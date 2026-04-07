# SPENDiD Application Architecture

This repository contains the SPENDiD service with a FastAPI backend, an MCP tool server, and OpenAI-based conversation flow.

## Flow Diagram

```mermaid
flowchart TD
    User[User / Browser]
    User --> |POST /chat| FastAPI[FastAPI app (`main.py`)]
    FastAPI --> |router -> chat_endpoint| Router[`app.api.endpoints.router`]
    Router --> |calls| ClientMain[`client.py -> main_streaming()`]
    ClientMain --> |load state| StateManager[StateManager (`session_data/sessions.json`)]
    ClientMain --> |intent prompt| OpenAIIntent[OpenAI intent classification]
    OpenAIIntent --> |returns intent| ClientMain
    ClientMain --> |if greeting| Greeting[Greeting prompt response]
    ClientMain --> |if QA| QA[QA prompt response]
    ClientMain --> |else payload| PayloadPrompt[Payload collection prompt]
    PayloadPrompt --> |tool call| MCPClient[MCP client session]
    MCPClient --> |calls| MCPServer[`server.py (MCP tool server)`]
    MCPServer --> |verify| VerifyLocation[`verify-zipcode-or-city-name`]
    MCPServer --> |payload update| AddPayload[`add-or-update-payload`]
    MCPServer --> |budget gen| GenerateBudget[`generate-budget`]
    MCPServer --> |budget update| UpdateCategory[`update-budget-category`]
    AddPayload --> |calls| WorkflowEngine[`app.workflow.engine.WorkflowEngine`]
    WorkflowEngine --> |update state| StateManager
    WorkflowEngine --> |check completeness| StateManager
    WorkflowEngine --> |external APIs| ExternalAPIs[External budget/financial APIs]
    ExternalAPIs --> |results| WorkflowEngine
    WorkflowEngine --> |api_results| StateManager
    ClientMain --> |format response| OpenAIResponse[OpenAI response prompt]
    OpenAIResponse --> |stream| User
    ClientMain --> |done event| User
    User --> |GET /state| FastAPI
    FastAPI --> |calls| GetStateEndpoint[router.get(`/state/{session_id}`)]
    GetStateEndpoint --> |returns| StateManager
```

## Overview

- `main.py` starts the FastAPI application and serves the UI.
- `app/api/endpoints.py` defines the `/chat` and `/state/{session_id}` endpoints.
- `client.py` handles conversation flow, OpenAI calls, and MCP tool invocation.
- `server.py` exposes MCP tools for location verification, payload updates, budget generation, and category updates.
- `app/state/state_manager.py` persists session state in `session_data/sessions.json`.
- `app/workflow/engine.py` orchestrates budget API calls and result generation.

## Notes

- The `/chat` endpoint streams AI responses back to the client.
- The `/state/{session_id}` endpoint returns current session state.
- Required environment variables are loaded via `.env`.
