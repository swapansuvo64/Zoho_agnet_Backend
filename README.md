# Zoho Agent Backend Services

Welcome to the backend of the **Zoho Agent** platform. This repository contains a modular, containerized multi-service ecosystem designed to orchestrate intelligent AI agents capable of interacting with the Zoho Projects API, managing user authentication, and storing context dynamically across sessions using short-term and long-term memory.

---

## 🛠️ Technology Stack & Core Decisions

The backend architecture is built using a modern, scalable, and highly performant stack. The choosing of key technologies is driven by specific engineering requirements:

### The Tech Stack
* **Language & Framework**: Python 3.11+ with **FastAPI** (asynchronous, high performance, native WebSocket support).
* **AI Orchestration**: **LangChain** (agent loops, structured routing) and **Google Gemini 2.5** (Pro/Flash).
* **Vector Embeddings**: **SentenceTransformers** (highly performant local backup embedding framework).
* **Caching & State**: **Redis** (session store, token caching, fast message queue).
* **Relational DB**: **Supabase** (PostgreSQL engine for relational data, users, tokens, and schemas).
* **Vector Database**: **ChromaDB** (local vector indexer for fast semantic search).
* **Containerization**: **Docker & Docker Compose** (infrastructure abstraction).

---

### 💡 Core Decisions: Why These Technologies?

#### 1. Why Google Gemini 2.5?
* **Massive Context Window**: Allows the agent to ingest extensive project histories, documents, and complex conversation threads without truncating critical context.
* **Precise JSON Schema Compliance**: Our autonomous agent planning (ReAct Loop) relies heavily on parsing structured JSON decisions (`thought`, `decision`, `query_tool`, `write_actions`, `final_response`). Gemini 2.5 delivers consistent structural schema formatting without parser errors.
* **Native Tool-Calling & Strong Reasoning**: Excels in understanding implicit relationships between distinct entities and planning dependencies (e.g., figuring out that updating a task requires listing project members to translate a name into a user ID first).
* **Speed & Cost Efficiency**: Minimal latency makes WebSocket conversational chat extremely snappy.

#### 2. Why ChromaDB?
* **Lightweight & Fully Embeddable**: Unlike heavy-weight cluster vector databases (such as Milvus or Qdrant), Chroma runs with minimal memory overhead inside a single docker container, keeping local development snappy.
* **Dynamic Ephemeral Collections**: Chroma provides native support for generating and destroying ephemeral collections on-the-fly, which fits our session-scoped Short-Term Memory (`session_{session_id}`) design perfectly.
* **Flexible Filtering**: Allows robust per-user segregation (`ltm_{user_id}`) and clean metadata queries (separating individual turn messages from aggregated session summaries).

#### 3. Why Docker?
* **Environment Consistency**: Eliminates "works on my machine" issues by standardizing operating system runtimes, Python packages, and libraries across macOS, Windows, and Linux.
* **Unified Infrastructure Orchestration**: Uses a singular compose file to control 5 different connected services (Auth, Zoho, Agent, Redis, Chroma) with a single command, automatically managing standard network bridges and dependencies.

---

## 🏗️ System Architecture


The backend consists of three core microservices, coordinated alongside **Redis** (caching), **Supabase** (persistent relational database), and **ChromaDB** (vector database for semantic search).

```
       ┌───────────────────────────────┐
       │     Vite Frontend Client      │
       └─────┬──────────────┬──────────┬┘
             │              │          │
 (OAuth/JWT) │  (Fetch API) │          │ (WebSockets/Chat)
             ▼              │          ▼
┌─────────────────────────┐ │  ┌─────────────────────────┐
│      Auth Service       │ │  │      Agent Service      │
│       (Port 8001)       │ │  │       (Port 8000)       │
└─────┬──────────────┬────┘ │  └────┬────────┬────────┬──┘
      │              │      │       │        │        │
      ▼              │      ▼       ▼        │        ▼
┌───────────┐        │ ┌──────────────┐      │  ┌───────────┐
│   Redis   │◄───────┼─┤ Zoho Service │      │  │ ChromaDB  │
│  (Cache)  │        │ │ (Port 8003)  │      │  │ (Vectors) │
└───────────┘        │ └──────────────┘      │  └───────────┘
      ▲              │                       │        ▲
      │              ▼                       ▼        │
      │        ┌───────────────────────────────┐      │
      └────────┤          Supabase DB          ├──────┘
               └───────────────────────────────┘
```


---

## 🚀 Getting Started & Services Setup

There are two primary ways to run the backend services: **Docker Compose (Recommended)** or **Manual Setup** via local virtual environments and start scripts.

### 📋 Prerequisites
Before running the services, create a `.env` file in each service subdirectory by copying the provided `.env.example` templates and filling in your credentials:
* **Agent Service**: `Backend/services/agent-service/.env`
* **Auth Service**: `Backend/services/auth-service/.env`
* **Zoho Service**: `Backend/services/zoho-service/.env`

---

### 📦 Option A: Running with Docker Compose (Recommended)

Docker Compose automatically spins up the application microservices along with pre-configured instances of Redis and ChromaDB. 

#### 💡 Architectural Insight: Why Redis & Chroma Use External Images
In `docker-compose.yml`, standard pre-compiled images (`redis:7-alpine` and `chromadb/chroma:latest`) are pulled directly from Docker Hub instead of building custom Dockerfiles:
* **Mature & Production-Ready**: These storage engines are mature, globally-tested database technologies. Rebuilding them from source is a waste of resource allocation and compile cycles.
* **Separation of Concerns (SoC)**: Keeps our code base focused purely on business-level application logic, delegating infrastructure orchestration to official pre-built minimal images (such as Alpine Linux for Redis).
* **Security & Footprint**: Official standard images are maintained, optimized, and vetted continuously for security patches and footprint reduction.

1. Navigate to the `Backend` directory:
   ```bash
   cd Backend
   ```
2. Build and start all services in the background:
   ```bash
   docker compose up -d --build
   ```
3. To view running containers and logs:
   ```bash
   docker compose ps
   docker compose logs -f
   ```
4. To stop the containers:
   ```bash
   docker compose down
   ```

---

### 🐍 Option B: Running Manually via Start Scripts

If you want to debug locally without Docker, you can run each service in its own terminal window. Each service contains virtual environment setup scripts tailored for your operating system (**Windows**, **macOS**, or **Ubuntu/Linux**).

For **each** service under `Backend/services/` (`agent-service`, `auth-service`, `zoho-service`):

#### 1. Setup Virtual Environment & Install Dependencies
Run the start script corresponding to your operating system. These scripts automatically create a virtual environment (`venv`), upgrade `pip`, install all dependencies listed in `requirements.txt`, and start the service.

* **Windows (PowerShell/CMD):**
  ```powershell
  cd Backend/services/<service-name>
  .\start.bat
  ```
* **macOS:**
  ```bash
  cd Backend/services/<service-name>
  chmod +x start_mac.sh
  ./start_mac.sh
  ```
* **Linux (Ubuntu/Debian):**
  ```bash
  cd Backend/services/<service-name>
  chmod +x start_ubuntu.sh
  ./start_ubuntu.sh
  ```

#### 2. Verify Port Allocations
Once all services are running, verify they are listening on the correct ports:
* **Agent Service**: `http://localhost:8000` (API & WebSockets)
* **Auth Service**: `http://localhost:8001` (OAuth & Session management)
* **Zoho Service**: `http://localhost:8003` (Zoho wrapper API for frontend)

---

## 🛠️ Microservice Directory & Roles

| Service | Port | Primary Language / Framework | Description |
| :--- | :---: | :--- | :--- |
| **Auth Service** | `8001` | Python (FastAPI) | Manages Zoho OAuth 2.0 flow, handles user profiles in Supabase, stores session tokens in Redis, and issues HTTP-Only secure JWT cookies. Runs a background cron to rotate expired tokens. |
| **Zoho Service** | `8003` | Python (FastAPI) | A lightweight REST wrapper around the Zoho Projects API. Receives JWT-authenticated calls from the frontend, queries `auth-service` for fresh credentials, and proxies requests securely. |
| **Agent Service** | `8000` | Python (FastAPI + WebSockets) | The central intelligence node. Orchestrates agents and sub-agents, manages Short-Term Memory (Redis/Chroma) and Long-Term Memory (Supabase/Chroma), executes tool tasks, and handles real-time agent chat over WebSockets. |

---

## 🔴 How Redis Works Across All Services

Redis acts as a high-speed, distributed in-memory data store that links all three backend microservices together. It ensures high performance by preventing repeated database queries and external Zoho API overhead.

```
┌────────────────────────────────────────────────────────────────────────┐
│                              REDIS CACHE                               │
├──────────────────────────────────┬─────────────────────────────────────┤
│ KEY FORMAT                       │ PURPOSE & BEHAVIOR                  │
├──────────────────────────────────┼─────────────────────────────────────┤
│ token:{user_id}                  │ Caches decrypted Zoho Access        │
│                                  │ Tokens. (TTL: 1 hour)               │
├──────────────────────────────────┼─────────────────────────────────────┤
│ session_refresh:{user_id}        │ Stores active app-specific JWT      │
│                                  │ Refresh Tokens. Used for rotation.  │
├──────────────────────────────────┼─────────────────────────────────────┤
│ chat_history:{session_id}        │ Appends list-cache of short-term    │
│                                  │ chat turns for real-time websocket. │
└──────────────────────────────────┴─────────────────────────────────────┘
```

1. **Token Caching (`token:{user_id}`)**:
   * When a service needs to query Zoho, it checks Redis first.
   * If the access token is cached, it is used immediately. If not, `auth-service` retrieves the encrypted refresh token from Supabase, decrypts it using a secure Fernet key, gets a new access token from Zoho, and caches it back in Redis for **3600 seconds (1 hour)**.

2. **Session Security & Refresh Token Rotation (`session_refresh:{user_id}`)**:
   * Used to enforce strict, secure session rotations. It tracks valid app JWT refresh tokens and guards against token reuse or replay attacks.

3. **Ephemeral Chat History Caching (`chat_history:{session_id}`)**:
   * Used by `agent-service` to temporarily cache recent chat messages during an active session (TTL: **24 hours**). This allows the agent to construct immediate conversation context instantly without running relational database queries on every socket frame.

---

## 🔐 Authentication & JWT Token Workflow

The system uses app-specific dual JWT tokens (`access_token` and `refresh_token`) stored securely inside `HttpOnly`, `Secure`, `SameSite=Lax` cookies, protecting them from Cross-Site Scripting (XSS) and Cross-Site Request Forgery (CSRF).

```
[ User/Frontend ]         [ Auth Service (8001) ]         [ Zoho API ]         [ Supabase DB ]         [ Redis Cache ]
       │                             │                         │                      │                       │
       │────── 1. GET /auth/login ──>│                         │                      │                       │
       │<───── 2. Redirect URL ──────│                         │                      │                       │
       │                             │                         │                      │                       │
       │─────────────── 3. Direct Authorization Consent ──────>│                      │                       │
       │<────────────── 4. Redirect with Auth CODE ────────────│                      │                       │
       │                             │                         │                      │                       │
       │────── 5. Forward CODE ─────>│                         │                      │                       │
       │                             │────── 6. Exchange ─────>│                      │                       │
       │                             │<───── 7. Zoho Tokens ───│                      │                       │
       │                             │                                                │                       │
       │                             │────── 8. Upsert user (portal ID, email) ──────>│                       │
       │                             │────── 9. Encrypt & store Zoho refresh token ──>│                       │
       │                             │                                                │                       │
       │                             │────── 10. Cache Zoho access token (1h TTL) ───────────────────────────>│
       │                             │────── 11. Cache JWT refresh token ────────────────────────────────────>│
       │                             │                                                │                       │
       │<───── 12. Set HttpOnly JWT cookies & Redirect to Chat ───────────────────────│                       │
```


### JWT Validation & Cross-Service Interoperability
When the Frontend makes a call to the **Zoho Service** to load resource details:
1. The **Zoho Service** intercepts the request, reads the app JWT from cookies or headers, and verifies it locally using a shared `JWT_SECRET`.
2. It calls the **Auth Service** internally via `GET /auth/zoho/token`, providing the verified user identity.
3. The **Auth Service** returns the active Zoho access token (fetching it from Redis or refreshing it from the database automatically).
4. The **Zoho Service** completes the proxy request directly to Zoho's REST API and returns the formatted response to the user.

---

## 🧠 Memory Architecture: STM & LTM

To create a natural conversation experience, the **Agent Service** implements a dual-memory layer combining short-term contextual caching with long-term vector search.

```
                           ┌──────────────────────────┐
                           │    User Input Message    │
                           └────────────┬─────────────┘
                                        │
                 ┌──────────────────────┴──────────────────────┐
                 ▼                                             ▼
     ┌───────────────────────┐                     ┌───────────────────────┐
     │   Short-Term Memory   │                     │   Long-Term Memory    │
     │      (Ephemeral)      │                     │     (Persistent)      │
     ├───────────────────────┤                     ├───────────────────────┤
     │ • Redis Cache         │                     │ • Supabase tables     │
     │ • Ephemeral Chroma    │                     │   (chat_history &     │
     │   Collection          │                     │   chat_summaries)     │
     │   (session_ID)        │                     │ • Persistent Chroma   │
     │                       │                     │   Collection          │
     │                       │                     │   (ltm_user_ID)       │
     └───────────┬───────────┘                     └───────────┬───────────┘
                 │                                             │
                 └──────────────────────┬──────────────────────┘
                                        ▼
                           ┌──────────────────────────┐
                           │ Hybrid Re-ranking        │
                           │ 70% Semantic (Cosine)    │
                           │ 30% Keywords (Jaccard)   │
                           └────────────┬─────────────┘
                                        ▼
                           ┌──────────────────────────┐
                           │ Sent to LLM Orchestrator │
                           └──────────────────────────┘
```

### 1. Short-Term Memory (STM)
* **Storage**: Redis lists (`chat_history:{session_id}`) + Ephemeral session collections in ChromaDB (`session_{session_id}`).
* **Lifecycle**: Generated when a WebSocket session initializes. Completely deleted from Chroma and Redis upon session close or user logout.
* **Context Retrieval (Hybrid Re-ranking)**:
  When searching for recent context, Chroma yields semantic candidates using Cosine Similarity. The service then performs a localized **Jaccard similarity** (keyword overlap comparison).
  $$\text{Combined Score} = (0.7 \times \text{Cosine Similarity}) + (0.3 \times \text{Jaccard Similarity})$$
  This hybrid re-ranking ensures the agent correctly recalls precise exact-match terms (like task/project IDs) as well as broad contextual meanings.

### 2. Long-Term Memory (LTM)
* **Storage**: Supabase Tables (`chat_history` & `chat_summaries`) + Persistent user collections in ChromaDB (`ltm_{user_id}`).
* **Lifecycle**: Indefinite / Persistent.
* **Real-time Persistence**: 
  Instead of waiting for the session to end, a background thread immediately triggers `write_message_to_ltm` after every message turn. It gets the sentence embeddings and upserts them into Chroma (`ltm_{user_id}`) so they are available cross-session instantly.
* **Vectorized Summaries**: 
  When a session closes, the Chat Summary Agent synthesizes the overall conversation and updates a singular summary document in Chroma (`summary_{session_id}` in `ltm_{user_id}`) to give the agent high-level historical visibility without bloating vector memory.

---

## 🤖 AI Agents & Tools Framework

The agent logic relies on a hierarchical multi-agent pattern. An **Orchestrator Agent** evaluates user intent and routes the task execution to specialized sub-agents equipped with tools.

### The Agents Ecosystem
1. **Orchestrator Agent (`orchestrator_agent.py`)**: 
   The brain. Conducts task parsing, manages flow control, queries STM/LTM memory, and routes requests to the Main, Query, or Action agents depending on user intent.
2. **Main Agent (`main_agent.py`)**: 
   Responsible for formatting conversational responses and maintaining natural back-and-forth dialogue with the user.
3. **Query Agent (`query_agent.py`)**: 
   Specialized in gathering, reading, and filtering data from Zoho Projects. Analyzes the workspace state by matching query tools.
4. **Action Agent (`action_agent.py`)**: 
   Specialized in executing write commands/mutations on Zoho (creating tasks, archiving projects, commenting).
5. **Chat Summary Agent (`chat_summary_agnet.py`)**: 
   Triggered to parse user chats to extract projects mentioned, tasks discussed, and actions taken, saving a structural summary to Supabase and Chroma.

### 🔄 Stepwise Agent Planning & ReAct Execution Loop

Complex, multi-step actions (such as *"Find all high priority tasks in the active project and assign them to Sarah and add a comment saying 'Urgent'"*) are orchestrated using an **autonomous ReAct (Reasoning and Acting) loop** within the `OrchestratorAgent`.

```
    ┌──────────────────────────────────────────────────────────────┐
    │                        User Request                          │
    └──────────────────────────────┬───────────────────────────────┘
                                   ▼
                 ┌───────────────────────────────────┐
                 │       Orchestrator ReAct Loop     │◄─────────────────┐
                 │       (Up to 6 sequential turns)  │                  │
                 └─────────────────┬─────────────────┘                  │
                                   │                                    │
                       Is more context needed?                          │
                                   ├─────────────────► [Action: call_query]
                                   │                   • Runs list_tasks, get_members, etc.
                                   │                   • Appends output to planning scratchpad
                                   ▼
                     All necessary data gathered?
                                   │
                                   ▼
                     [Action Decision: plan_write]
                                   │
                                   ▼
                ┌─────────────────────────────────────┐
                │ Batching Writes & Caching in Redis  │
                │  (pending_actions:{session_id})     │
                └──────────────────┬──────────────────┘
                                   │
                                   ▼
                ┌─────────────────────────────────────┐
                │ Human-in-the-Loop Confirmation Card │
                └──────────────────┬──────────────────┘
                                   │
                         Does User Confirm?
                                   ├─────────────────► Cancelled: Clear cache & abort.
                                   ▼
                     [Action Approved: Execute]
                                   │
                                   ▼
                ┌─────────────────────────────────────┐
                │   Parallel Writes (asyncio.gather)  │
                └──────────────────┬──────────────────┘
                                   ▼
                ┌─────────────────────────────────────┐
                │   Structured execution table report │
                └─────────────────────────────────────┘
```

#### Detailed Step-by-Step Flow:
1. **Context Synthesis**: The Orchestrator gathers the system clock, recent Short-Term Memory context, and high-level conversation summaries, formatting them into the prompt.
2. **The ReAct Planning Iterations** (Up to 6 loops):
   * **Reason (Thought)**: Evaluates what information is still missing from the local context.
   * **Act (Query Execution)**: Decides to query a read-only tool (e.g., `list_project_members` or `list_tasks`). It runs the tool, appends the output to the history log, and loops.
3. **Transaction Batching & Redis Caching**:
   * Once the goal is formulated and actions mapped out, the Orchestrator prepares the write mutations.
   * Rather than executing them instantly (which could lead to corrupted or partially applied states), it structures the planned operations into a single transactional payload and caches it in Redis under `pending_actions:{session_id}` (5-minute TTL).
4. **Human-in-the-Loop Safeguard**:
   * The agent renders a beautiful **Interactive Confirmation Card** directly in the chat window, detailing every proposed mutation alongside custom deep-links (e.g. `task://{project_id}/{task_id}`).
5. **Parallel Execution Engine (`asyncio.gather`)**:
   * If the user approves, `execute_pending_actions` is invoked.
   * The service retrieves the payload, clears the Redis cache, and executes all write operations (e.g. `create_task`, `add_task_comment`) concurrently using standard Python `asyncio.gather`.
   * This parallelized execution maximizes backend throughput, resolving network tasks in milliseconds.
   * A structured markdown execution report table is compiled and sent to the frontend for display.

---

### 🔧 Available Tools
Agents automatically select and execute these Python-based tool definitions inside the `Backend/services/agent-service/src/tools` directory to read and write data in Zoho:

```
agent-service/src/tools/
├── query/
│   ├── list_projects.py         # Retrieves active Zoho Projects for the portal
│   ├── list_tasks.py            # Lists all tasks associated with a project ID
│   ├── get_task_details.py      # Retrieves details of a specific task
│   ├── get_task_comments.py     # Pulls developer and member comments from a task
│   ├── list_project_members.py  # Lists members assigned to a project
│   └── get_task_utilisation.py  # Calculates team members' hours and allocations
└── action/
    ├── create_project.py        # Spins up a new project workspace in Zoho
    ├── update_project.py        # Modifies project metadata (status, owner, dates)
    ├── delete_project.py        # Permanently removes/archives a project
    ├── create_task.py           # Creates a new task inside a project
    ├── update_task.py           # Updates task status, assignee, or priority
    ├── delete_task.py           # Deletes a task from a project
    └── add_task_comment.py      # Submits developer comments to a task
```

---

## 🔒 Security Best Practices
* **Encryption**: Zoho Refresh Tokens are encrypted in transit and at rest using standard **Fernet (AES-128)** encryption. The key is managed via `ENCRYPTION_KEY` in the environment variables.
* **HttpOnly Cookies**: Prevents client-side scripts from reading the JWT session cookies, blocking standard XSS steal vectors.
* **Minimal Scope**: The agent token cache restricts access purely to the portal IDs retrieved at the time of user authentication.
