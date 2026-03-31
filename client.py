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
    
    final_intent_prompt = INTENT_PROMPT.format(current_payload=current_payload, user_message=user_text)
    intent_res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": final_intent_prompt}],
        temperature=0
    )
    intent = intent_res.choices[0].message.content.strip().lower()
    # print(f"Intent: {intent}")

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as mcp_session:
            await mcp_session.initialize()
            tools_resp = await mcp_session.list_tools()
            openai_tools = [
                {"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.inputSchema}}
                for t in tools_resp.tools
            ]

            # 2. Handle Intent
            if "qa" in intent:
                from app.prompts.qa import QA_PROMPT
                final_prompt = QA_PROMPT.format(state=current_payload, api_results=current_payload.get("api_results", {}), history=history_str, user_message=user_text)
                stream = client.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": final_prompt}], stream=True)
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
                model="gpt-4o",
                messages=[{"role": "system", "content": prompt}, {"role": "user", "content": user_text}],
                tools=openai_tools,
                tool_choice="auto"
            )
            
            msg = response.choices[0].message
            if msg.tool_calls:
                tool_call = msg.tool_calls[0]
                args = json.loads(tool_call.function.arguments)
                tool_name = tool_call.function.name
                args['session_id'] = session_id
                
                # Special handling for location verification
                if tool_name == "verify-zipcode-or-city-name":
                    content = await mcp_session.call_tool(tool_name, arguments=args)
                    verify_data = json.loads(content.content[0].text)
                    if not verify_data.get("error"):
                        tool_name = "add-or-update-payload"
                        args = {"session_id": session_id, "zipcode": str(verify_data.get("zip_code"))}
                
                tool_res = await mcp_session.call_tool(tool_name, arguments=args)
                data = json.loads(tool_res.content[0].text)
                
                if "api_results" in data:
                    sm.update(session_id, {"api_results": data["api_results"]})
                elif "budget_data" in data:
                    sm.update(session_id, {"api_results": data})
                
                updated_state = sm.get(session_id)
                format_response = RESPONSE_PROMPT.format(
                    state=updated_state, api_results=updated_state.get("api_results", {}),
                    next_fields=data.get("next_fields", []), history=history_str
                )
                stream = client.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": format_response}], stream=True)
                full_reply = ""
                for chunk in stream:
                    content = chunk.choices[0].delta.content or ""
                    if content:
                        full_reply += content
                        yield json.dumps({"type": "chunk", "content": content}) + "\n"
                maintain_history(session_id, user_text, full_reply)
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