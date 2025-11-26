Portfolio (Symbol) research flow

Reporter Lambda (Agent) 
     |
     | submit_portfolio_research_job()
     v
SQS Queue  <---- retry, DLQ support
     |
     | (1 message per symbol)
     v
Research Worker Lambda  <-- NEW
     |
     | POST /research/symbol
     v
Researcher App Runner
     |
     | ingest → embeddings → S3 vectors
     v
JobTracker (Aurora)

Here's how it fits into the Alex architecture:

```mermaid
graph TD

%% ================== LAYERS ==================

%% ---- Reporter & User Layer ----
USER["**User**"]
REP["**Reporter Agent**<br/>(Builds Reports)"]

%% ---- Portfolio & DB Layer ----
DB["**Aurora DB**<br/>User Accounts & Holdings"]

%% ---- Async Queue Layer ----
Q["**SQS Queue**<br/>portfolio-research-requests"]
JOB["**Job Tracker**<br/>(Aurora or DynamoDB)"]

%% ---- Researcher Layer ----
RES["**Researcher Agent**<br/>(Bedrock + Web Search)"]

%% ---- Market Outlook (Daily Global Research) ----
SCHED["**Scheduler Lambda**<br/>(Daily Global Outlook)"]

%% ---- LLM & Ingestion ----
BED["**Bedrock LLM + Web MCP**"]
ING["**Ingest API**<br/>(Lambda + SageMaker Embeddings)"]
S3V["**S3 Vectors**<br/>alex-vectors"]

%% ---- Retrieval Layer ----
RET["**Semantic Retrieval**<br/>(SageMaker Endpoint)"]

%% ================== FLOWS ==================

%% User asks for report
USER -->|"Request Portfolio Report"| REP

%% Reporter queries DB for portfolio
REP -->|"Load User Holdings"| DB

%% Reporter creates async jobs per symbol
REP -->|"Enqueue {user, account, symbol}"| Q
REP -->|"Create Job Record"| JOB

%% Researcher consumes async tasks
Q -->|"SQS Trigger (1 symbol per message)"| RES
RES -->|"Run Symbol-Specific Research"| BED
BED -->|"Analysis Text"| RES

%% Researcher stores insights
RES -->|"Ingest with Metadata"| ING
ING -->|"Embeddings Stored"| S3V
RES -->|"Mark Symbol Done"| JOB

%% Reporter polls job status
JOB -->|"Check if all symbols complete"| REP

%% Reporter retrieves final insights
REP -->|"Query S3 Vectors"| RET
RET -->|"Combined Macro + Symbol Insights"| REP

%% Global daily market outlook (existing)
SCHED -->|"Trigger Daily Global Outlook"| RES
RES -->|"Ingest Global Market Outlook"| ING

%% ================== STYLING ==================

style USER fill:#ffffff,stroke:#1f2937,stroke-width:2px,color:#000,fontWeight:bold
style REP fill:#ffffff,stroke:#1f2937,stroke-width:2px,color:#000,fontWeight:bold
style DB fill:#ffffff,stroke:#1d4ed8,stroke-width:2px,color:#000,fontWeight:bold

style Q fill:#fff7ed,stroke:#c2410c,stroke-width:2px,color:#000,fontWeight:bold
style JOB fill:#fff7ed,stroke:#c2410c,stroke-width:2px,color:#000,fontWeight:bold

style RES fill:#faf5ff,stroke:#7e22ce,stroke-width:2px,color:#000,fontWeight:bold
style SCHED fill:#faf5ff,stroke:#7e22ce,stroke-width:2px,color:#000,fontWeight:bold

style BED fill:#f0f9ff,stroke:#0369a1,stroke-width:2px,color:#000,fontWeight:bold
style ING fill:#f0fdf4,stroke:#15803d,stroke-width:2px,color:#000,fontWeight:bold
style S3V fill:#dcfce7,stroke:#15803d,stroke-width:2px,color:#000,fontWeight:bold

style RET fill:#fef9c3,stroke:#ca8a04,stroke-width:2px,color:#000,fontWeight:bold

```
Updated Mermaid Architecture Diagram

```mermaid
graph TD

USER["**User**"]
REP["**Reporter Agent**<br/>App Runner"]
DB["**Aurora DB**<br/>Accounts, Positions, JobTracker"]
SQS["**SQS**<br/>portfolio-research"]
DLQ["**DLQ**"]
RES["**Researcher Agent**<br/>App Runner (SQS Consumer)"]
ING["**Ingest Pipeline**<br/>Lambda + SageMaker"]
S3V["**S3 Vectors**"]
RET["**Semantic Retrieval**<br/>SageMaker"]
SCHED["**Daily Scheduler**<br/>Lambda"]

USER -->|"Request Report"| REP
REP -->|"Load Portfolio"| DB

REP -->|"Submit job per symbol"| SQS
SQS -->|"Retries → DLQ"| DLQ

RES -->|"Consume 1 symbol message"| SQS
RES -->|"Research AAPL or MSFT"| ING
ING -->|"Embeddings"| S3V
RES -->|"Mark symbol done"| DB

REP -->|"Poll job status"| DB
REP -->|"Retrieve insights"| RET
RET -->|"Contextual vectors"| REP

SCHED -->|"Daily market outlook"| RES

```

Mermaid Sequence Diagram (End-to-End Flow)

```mermaid

sequenceDiagram
    participant U as User
    participant R as Reporter
    participant DB as Aurora DB
    participant Q as SQS Queue
    participant S as Researcher
    participant I as Ingest Pipeline
    participant V as S3 Vectors

    U->>R: Request Portfolio Report
    R->>DB: Fetch Portfolio Symbols
    DB-->>R: ["AAPL","MSFT","NVDA"]

    R->>DB: Create job_tracker + items
    R->>Q: Enqueue {job_id, AAPL}
    R->>Q: Enqueue {job_id, MSFT}
    R->>Q: Enqueue {job_id, NVDA}

    S->>Q: ReceiveMessage (AAPL)
    Q-->>S: Message(AAPL)

    S->>DB: mark_symbol_running(AAPL)
    S->>S: run_symbol_research(AAPL)
    S->>I: ingest_financial_document(AAPL)
    I->>V: Store embedding for AAPL
    S->>DB: mark_symbol_done(AAPL)

    S->>Q: ReceiveMessage (MSFT)
    Q-->>S: Message(MSFT)

    S->>DB: mark_symbol_running(MSFT)
    S->>S: run_symbol_research(MSFT)
    S->>I: ingest_financial_document(MSFT)
    I->>V: Store embedding for MSFT
    S->>DB: mark_symbol_done(MSFT)

    S->>Q: ReceiveMessage (NVDA)
    Q-->>S: Message(NVDA)

    S->>DB: mark_symbol_running(NVDA)
    S->>S: run_symbol_research(NVDA)
    S->>I: ingest_financial_document(NVDA)
    I->>V: Store embedding for NVDA
    S->>DB: mark_symbol_done(NVDA)

    R->>DB: Poll job_tracker
    DB-->>R: All symbols done

    R->>V: Retrieve insights via semantic search
    V-->>R: Combined context

    R->>U: Produce final report

```

Updated Architecture diagram

```mermaid
graph TD

U[User or Trader Agents]
DB[(Aurora Database)]

U --> DB
DB --> RPT[Reporter Lambda]

subgraph Reporter_Layer
    RPT
end

subgraph Submit_Research_Jobs
    RPT --> SQS[(Symbol Research SQS)]
end

subgraph Symbol_Worker
    SQS --> WORKER[Worker Lambda]
end

subgraph Researcher_Service
    WORKER --> RES[Researcher App Runner]
end

subgraph Ingestion_Pipeline
    RES --> INGEST[Ingest Lambda]
    INGEST --> SM[SageMaker Embeddings]
    SM --> S3V[S3 Vector Store]
end

subgraph Retrieval
    S3V --> RET[Vector Retrieval]
    RET --> RPT
end

subgraph Daily_Outlook
    EB[EventBridge Scheduler] --> SCHEDLAMBDA[Scheduler Lambda]
    SCHEDLAMBDA --> RES
end

subgraph Job_Tracker
    WORKER --> JT[(Job Tracker Tables)]
    RPT --> JT
end

```

Updated Sequence diagram
```mermaid
sequenceDiagram
    autonumber

    participant RPT as Reporter Lambda
    participant SQS as Symbol Research SQS
    participant WRK as Worker Lambda
    participant RES as Researcher Service
    participant ING as Ingest Lambda
    participant SM as SageMaker
    participant S3 as S3 Vectors
    participant JT as JobTracker

    RPT->>JT: init_job(job_id, symbols)
    JT-->>RPT: ack

    loop for each symbol
        RPT->>SQS: enqueue {job_id, symbol}
    end

    SQS->>WRK: trigger worker
    WRK->>JT: mark_symbol_running

    WRK->>RES: POST /research/symbol
    RES-->>WRK: symbol analysis

    WRK->>ING: ingest analysis
    ING->>SM: create embeddings
    SM->>S3: store vectors

    WRK->>JT: mark_symbol_done

    loop until all symbols complete
        RPT->>JT: check_research_job_status
        JT-->>RPT: status
    end

    RPT->>RES: get_market_insights(symbols)
    RES->>S3: query vectors
    S3->>RES: enriched insights

    RPT->>RPT: generate final report


```