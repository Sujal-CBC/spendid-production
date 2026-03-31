from openai import OpenAI 
import os, json, sys, asyncio
from dotenv import load_dotenv  
from mcp.client.stdio import stdio_client, StdioServerParameters 
from mcp import ClientSession 
from app.prompts.intent import INTENT_PROMPT  
from app.prompts.payload import COLLECTION_PROMPT
from app.prompts.response import RESPONSE_PROMPT
from app.state.state_manager import StateManager 

load_dotenv() 
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
sm = StateManager()

# Helper to keep only last 3 exchanges
def maintain_history(session_id, user_msg, ai_msg):
    if not hasattr(maintain_history, "storage"):
        maintain_history.storage = {}
    
    if session_id not in maintain_history.storage:
        maintain_history.storage[session_id] = []
    
    history = maintain_history.storage[session_id]
    if user_msg:
        history.append(f"user: {user_msg}")
    if ai_msg:
        history.append(f"ai: {ai_msg}")
    
    # Keep only last 6 lines (3 turns)
    maintain_history.storage[session_id] = history[-6:]
    return "\n".join(maintain_history.storage[session_id])

maintain_history.storage = {}

async def main(user_text: str, session_id: str):
    server = StdioServerParameters(
        command=sys.executable,
        args=["server.py"] 
    )
    async with stdio_client(server) as (read_stream, write_stream):     
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize() 
            
            # 1. Fetch MCP Tools
            tools_resp = await session.list_tools() 
            openai_tools = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description, 
                        "parameters": tool.inputSchema
                    }
                } for tool in tools_resp.tools
            ]

            # 2. Intent Classification
            current_payload = sm.get(session_id)
            final_intent_prompt = INTENT_PROMPT.format(
                current_payload=current_payload, 
                user_message=user_text
            )
            
            # Use gpt-4o for better reasoning
            intent_res = client.chat.completions.create(
                model="gpt-4o-mini", 
                messages=[{"role": "system", "content": final_intent_prompt}],
                temperature=0
            )
            intent = intent_res.choices[0].message.content.strip().lower()

            history_list = maintain_history.storage.get(session_id, [])
            history_str = "\n".join(history_list)
            
            # --- INTENT HANDLERS ---
            print(f"Intent: {intent}")
            # 1. QA Intent
            if "qa" in intent:
                from app.prompts.qa import QA_PROMPT
                final_prompt = QA_PROMPT.format(
                    state=current_payload,
                    api_results=current_payload.get("api_results", {}),
                    history=history_str,
                    user_message=user_text
                )
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "system", "content": final_prompt}]
                )
                final_text = response.choices[0].message.content
                maintain_history(session_id, user_text, final_text)
                return final_text

            # 2. Payload / Collection / Generate / Update / Regenerate
            if "payload" in intent or "regenerate" in intent:
                final_payload_prompt = COLLECTION_PROMPT.format(
                    current_payload=current_payload,
                    chat_history=history_str,
                )
            elif "generate" in intent:
                final_payload_prompt = f"The user is ready to generate their budget. Call the `generate-budget` tool.\nContext: {current_payload}"
            elif "update" in intent:
                final_payload_prompt = f"The user wants to update a budget category. Call the `update-budget-category` tool.\nContext: {current_payload}\nHistory: {history_str}"
            else:
                final_payload_prompt = COLLECTION_PROMPT.format(
                    current_payload=current_payload,
                    chat_history=history_str,
                )

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                temperature=0.0, # Lower temperature for tool calls
                messages=[
                    {"role": "system", "content": final_payload_prompt},
                    {"role": "user", "content": user_text}
                ],
                tools=openai_tools,
                tool_choice="auto"
            )
            
            ai_message = response.choices[0].message
            
            # Case A: Tool call is generated
            if ai_message.tool_calls: 
                print("Executing tool calls...")
                # For simplicity, we handle the first tool call in the chain
                tool_call = ai_message.tool_calls[0]
                args = json.loads(tool_call.function.arguments)  
                tool_name = tool_call.function.name  
                args['session_id'] = session_id
                
                print(f"Tool: {tool_name}, Args: {args}")
                
                if tool_name == "verify-zipcode-or-city-name": 
                    content = await session.call_tool(tool_name, arguments=args) 
                    try:
                        verify_data = json.loads(content.content[0].text)
                    except (json.JSONDecodeError, IndexError):
                        return "Invalid response from location verification."
                    
                    if verify_data.get("error"):
                        return "Invalid zipcode or city. Please try again."
                    
                    tool_name = "add-or-update-payload"
                    args = {
                        "session_id": session_id,
                        "zipcode": str(verify_data.get("zip_code", args.get("city_or_zip")))
                    }
                
                # Execute final tool
                content = await session.call_tool(tool_name, arguments=args)
                raw_text = content.content[0].text
                try:
                    data = json.loads(raw_text)
                except json.JSONDecodeError:
                    return f"Error processing tool output: {raw_text[:100]}"
                
                # IMPORTANT: Update StateManager with results, avoiding recursion
                if "api_results" in data:
                    # If it's a process() output, extract only the results
                    results_to_store = data["api_results"]
                    sm.update(session_id, {"api_results": results_to_store})
                elif "budget_data" in data:
                    sm.update(session_id, {"api_results": data})
                
                updated_state = sm.get(session_id)
                next_fields = data.get("next_fields", [])
                _, missing = sm.is_complete(session_id)
                if not next_fields: next_fields = missing

                format_response = RESPONSE_PROMPT.format(
                    state=updated_state,
                    api_results=updated_state.get("api_results", {}),
                    next_fields=next_fields,
                    history=history_str
                )
                
                final_res = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{"role":"system","content":format_response}]
                )
                final_text = final_res.choices[0].message.content
                maintain_history(session_id, user_text, final_text)
                return final_text
            
            # Case B: No tool call, but LLM might have answered or needs to ask a follow-up
            else:
                updated_state = sm.get(session_id)
                _, missing = sm.is_complete(session_id)
                
                # Re-format using RESPONSE_PROMPT to ensure consistency
                format_response = RESPONSE_PROMPT.format(
                    state=updated_state,
                    api_results=updated_state.get("api_results", {}),
                    next_fields=missing,
                    history=history_str
                )
                
                # We include the LLM's raw thought/answer as a hint
                final_res = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role":"system","content":format_response},
                        {"role":"assistant","content":ai_message.content or ""},
                        {"role":"user","content": "Please continue the conversation naturally based on the current state."}
                    ]
                )
                final_text = final_res.choices[0].message.content
                maintain_history(session_id, user_text, final_text)
                return final_text

if __name__ == "__main__":
    while True: 
        query = input("Enter your query : ")
        if query.lower() in ("exit", "quit"): break
        res = asyncio.run(main(query, "123")) 
        print("SPENDiD-BOT : ",res)