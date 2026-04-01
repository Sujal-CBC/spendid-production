from openai import OpenAI 
import os, json, sys, asyncio
from dotenv import load_dotenv  
from mcp.client.stdio import stdio_client, StdioServerParameters 
from mcp import ClientSession 
from app.prompts.intent import INTENT_PROMPT  
from app.prompts.payload import COLLECTION_PROMPT
from app.prompts.response import RESPONSE_PROMPT, UPDATE_RESPONSE_PROMPT, REGENERATE_RESPONSE_PROMPT, BUDGET_SUMMARY_PROMPT 
from app.prompts.greeting import GREETING_PROMPT
from app.state.state_manager import StateManager 

load_dotenv() 
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), timeout=60.0)
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

async def main_streaming(user_text: str, session_id: str):
    """Async generator that yields JSON chunks for streaming UI."""
    import json
    import sys
    from mcp.client.stdio import stdio_client, StdioServerParameters
    from mcp import ClientSession

    server_params = StdioServerParameters(command=sys.executable, args=["server.py"])
    
    # 1. Intent Classification
    current_payload = sm.get(session_id)
    history_list = maintain_history.storage.get(session_id, [])
    history_str = "\n".join(history_list)
    
    final_intent_prompt = INTENT_PROMPT.format(current_payload=current_payload, user_message=user_text, history=history_str, api_results=current_payload.get("api_results", {}))
    intent_res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": final_intent_prompt}],
        temperature=0
    )
    intent = intent_res.choices[0].message.content.strip().lower() 
    print(f"User text : {user_text}")
    print(f"Intent: {intent}") # current intent   
    print(f"Current history : ",history_str)

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as mcp_session:
            await mcp_session.initialize()
            tools_resp = await mcp_session.list_tools()
            openai_tools = [
                {"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.inputSchema}}
                for t in tools_resp.tools
            ]

            # 2. Handle Intent
            if "greeting" in intent:  
                formated_prompt = GREETING_PROMPT.format(
                    history = history_str
                ) 
                response = client.chat.completions.create(
                    model="gpt-4o-mini", 
                    temperature=0.85,
                    messages=[
                        {"role":"system","content":formated_prompt},
                        {"role":"user","content":user_text}
                    ]
                ) 
                
                # Get the greeting response content
                full_reply = response.choices[0].message.content 
                
                # Yield the response (you can yield it all at once or simulate chunks)
                yield json.dumps({"type": "chunk", "content": full_reply}) + "\n"
                
                # Maintain conversation history
                maintain_history(session_id, user_text, full_reply)
                
                # Return done signal with current state
                yield json.dumps({"type": "done", "state": current_payload, "session_id": session_id}) + "\n"
                return
                
            if "qa" in intent:
                from app.prompts.qa import QA_PROMPT
                final_prompt = QA_PROMPT.format(state=current_payload, api_results=current_payload.get("api_results", {}), history=history_str, user_message=user_text)
                stream = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "system", "content": final_prompt}], stream=True)
                full_reply = ""
                for chunk in stream:
                    content = chunk.choices[0].delta.content or ""
                    if content:
                        full_reply += content
                        yield json.dumps({"type": "chunk", "content": content}) + "\n"
                maintain_history(session_id, user_text, full_reply)
                yield json.dumps({"type": "done", "state": current_payload, "session_id": session_id}) + "\n"
                return

            # Payload handle
            prompt = COLLECTION_PROMPT.format(current_payload=current_payload, chat_history=history_str)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "system", "content": prompt}, {"role": "user", "content": user_text}],
                tools=openai_tools,
                tool_choice="auto"
            )
            
            msg = response.choices[0].message 
            # print("Message for payload : ",msg)
            if msg.tool_calls:
                tool_call = msg.tool_calls[0]
                args = json.loads(tool_call.function.arguments)
                tool_name = tool_call.function.name
                args['session_id'] = session_id
                
                # Special handling for location verification
                # if tool_name == "verify-zipcode-or-city-name":
                #     args["session_id"] = session_id 
                #     content = await mcp_session.call_tool(tool_name, arguments=args) 
                #     verify_data = json.loads(content.content[0].text)  
                    # print(verify_data)
                    # response = client.chat.completions.create(
                    # )
                    
                
                tool_res = await mcp_session.call_tool(tool_name, arguments=args)
                data = json.loads(tool_res.content[0].text)
                if "api_results" in data:
                    sm.overwrite_api_results(session_id, data["api_results"])
                elif "budget_data" in data:
                    sm.overwrite_api_results(session_id, data)
                # print("data = ",data)
                # print("Intent after the toool call : ",intent) 
                if intent == "update": 
                    updated_state = sm.get(session_id)
                    maintain_history(session_id, user_text, "[processing]")
                    history_str = "\n".join(maintain_history.storage.get(session_id, []))
                    
                    format_response = UPDATE_RESPONSE_PROMPT.format(
                        state=updated_state, api_results=updated_state.get("api_results", {}),
                        history=history_str
                    ) 
                    stream = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "system", "content": format_response}], stream=True)
                    
                elif intent == "regenerate": 
                    updated_state = sm.get(session_id)
                    maintain_history(session_id, user_text, "[processing]")
                    history_str = "\n".join(maintain_history.storage.get(session_id, []))
                    
                    format_response = REGENERATE_RESPONSE_PROMPT.format(
                        state=updated_state, api_results=updated_state.get("api_results", {}),
                        history=history_str
                    ) 
                    stream = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "system", "content": format_response}], stream=True)
                    
                else:
                    updated_state = sm.get(session_id)
                    # Refresh history to include latest exchange
                    maintain_history(session_id, user_text, "[processing]")
                    history_str = "\n".join(maintain_history.storage.get(session_id, []))
                    
                    # Check if profile is now complete (next_fields is empty)
                    next_fields = data.get("next_fields", [])
                    if not next_fields or (isinstance(next_fields, list) and len(next_fields) == 0):
                        # Profile complete - budget was just generated, use summary prompt
                        format_response = BUDGET_SUMMARY_PROMPT.format(
                            state=updated_state, api_results=updated_state.get("api_results", {}),
                            history=history_str
                        )
                    else:
                        # Still collecting data
                        format_response = RESPONSE_PROMPT.format(
                            state=updated_state, api_results=updated_state.get("api_results", {}),
                            next_fields=next_fields, history=history_str
                        ) 
                    stream = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "system", "content": format_response}], stream=True)
                    
                print(f"Current payload : {sm.get(session_id)}")

                full_reply = ""
                for chunk in stream:
                    content = chunk.choices[0].delta.content or ""
                    if content:
                        full_reply += content
                        yield json.dumps({"type": "chunk", "content": content}) + "\n"
                # Update history with actual AI response (replaces [processing])
                maintain_history.storage[session_id][-1] = f"ai: {full_reply}"
                yield json.dumps({"type": "done", "state": updated_state, "session_id": session_id}) + "\n"
            else:
                full_reply = msg.content
                maintain_history(session_id, user_text, full_reply)
                yield json.dumps({"type": "chunk", "content": full_reply}) + "\n"
                yield json.dumps({"type": "done", "state": current_payload, "session_id": session_id}) + "\n" 

async def main(user_text: str, session_id: str):
    """Legacy sync-like wrapper for compatibility if needed."""
    full_text = ""
    async for chunk_str in main_streaming(user_text, session_id):
        data = json.loads(chunk_str)
        if data["type"] == "chunk":
            full_text += data["content"]
    return full_text

if __name__ == "__main__":
    async def test():
        async for chunk in main_streaming("hi", "123"):
            print(chunk, end="")
    asyncio.run(test()) 

# if __name__ == "__main__":
#     while True: 
#         query = input("Enter your query : ")
#         if query.lower() in ("exit", "quit"): break
#         res = asyncio.run(main_streaming(query, "123")) 
#         print("SPENDiD-BOT : ",res)