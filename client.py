from openai import OpenAI 
import os, json, sys, asyncio
from dotenv import load_dotenv  
from mcp.client.stdio import stdio_client, StdioServerParameters 
from mcp import ClientSession 
from app.prompts.intent import INTENT_PROMPT  
from app.prompts.payload import COLLECTION_PROMPT
from app.state.state_manager import StateManager

load_dotenv() 
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
sm = StateManager()

# Helper to keep only last 3 exchanges
def maintain_history(session_id, user_msg, ai_msg):
    # You should probably store this in your StateManager or a dict
    # For now, let's assume a simple list for the example
    if not hasattr(maintain_history, "storage"):
        maintain_history.storage = {}
    
    if session_id not in maintain_history.storage:
        maintain_history.storage[session_id] = []
    
    history = maintain_history.storage[session_id]
    history.append(f"user: {user_msg}")
    history.append(f"ai: {ai_msg}")
    
    # Keep only last 6 lines (3 turns)
    maintain_history.storage[session_id] = history[-6:]
    return "\n".join(maintain_history.storage[session_id])

async def main(user_text: str, session_id: str):
    server = StdioServerParameters(
        command=sys.executable,
        args=["server.py"] 
    )
    async with stdio_client(server) as (read_stream, write_stream):     
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize() 
            
            # 1. Fetch MCP Tools and convert to OpenAI Format
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
            
            intent_res = client.chat.completions.create(
                model="gpt-4o-mini", 
                messages=[{"role": "system", "content": final_intent_prompt}],
                temperature=0
            )
            intent = intent_res.choices[0].message.content.strip().lower()

            history_str = maintain_history(session_id, "", "") # Get existing
            # 3. Handle "Payload" Collection Intent
            if "payload" in intent:
                
                final_payload_prompt = COLLECTION_PROMPT.format(
                    current_payload=current_payload,
                    chat_history=history_str,
                    user_message=user_text
                )

                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": final_payload_prompt},
                        {"role": "user", "content": user_text}
                    ],
                    tools=openai_tools,
                    tool_choice="auto"
                )

                ai_message = response.choices[0].message
                
                # 4. Execute Tool if LLM requested it
                if ai_message.tool_calls:
                    for tool_call in ai_message.tool_calls:
                        f_name = tool_call.function.name
                        f_args = tool_call.function.arguments
                        
                        print(f"🛠️ Calling MCP Tool: {f_name} with {f_args}") 
                        return
                        # ACTUAL MCP CALL
                        result = await session.call_tool(f_name, arguments=f_args)
                        
                        # Update your local state so the next loop knows info is filled
                        current_payload.update(f_args)
                        sm.set(session_id, current_payload)

                # 5. Output to User & Update History
                final_text = ai_message.content or "Profile updated! What's next?"
                print(f"🤖 AI: {final_text}")
                maintain_history(session_id, user_text, final_text)

            else:
                print(f"Intent detected: {intent}. (Logic for update/regenerate/qa goes here)")

if __name__ == "__main__":
    asyncio.run(main("my age is 34", "123"))