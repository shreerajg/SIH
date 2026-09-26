# SIH 2026 - BIS Platform Backend Architecture Guide
## Complete Backend Understanding for Development Team

---

## 🏗️ **BACKEND TECHNOLOGY STACK**

- **Framework**: FastAPI (Python 3.8+)
- **Data Validation**: Pydantic v2
- **Database**: MongoDB with PyMongo (synchronous)
- **Vector Search**: MongoDB Atlas Vector Search + brute-force fallback
- **Embeddings**: sentence-transformers (all-MiniLM-L6-v2)
- **Keyword Search**: rank-bm25
- **Document Processing**: PyMuPDF for PDF parsing
- **OCR**: Tesseract via pytesseract
- **LLM Support**: Multi-provider (OpenAI/Anthropic/Gemini)
- **Async**: Standard FastAPI async/await patterns
- **Testing**: 274 tests including guardrails

---

## 📁 **BACKEND PROJECT STRUCTURE**

```
backend/
├── app/
│   ├── main.py                    # FastAPI application entry point
│   ├── api/                       # FastAPI routers (HTTP endpoints)
│   │   ├── __init__.py
│   │   ├── deps.py               # Dependency injection
│   │   ├── chat.py               # Chat/AI assistant endpoint
│   │   ├── evidence.py           # Evidence upload/management
│   │   ├── health.py             # System health/status
│   │   └── products.py           # Product analysis endpoints
│   ├── compliance/               # Gap analysis engine
│   │   ├── __init__.py
│   │   └── gap_analyzer.py       # Core compliance logic
│   ├── core/                     # Core configuration
│   │   ├── config.py             # Environment settings
│   │   └── constants.py          # System constants
│   ├── db/                       # Database layer
│   │   ├── mongo.py              # MongoDB connection
│   │   └── repositories/         # Data access layer
│   ├── ingestion/                # Document processing
│   │   ├── pipeline.py           # Main ingestion pipeline
│   │   └── seed.py               # Database seeding
│   ├── llm/                      # LLM abstraction layer
│   │   ├── base.py               # Base LLM interface
│   │   ├── providers.py          # Provider implementations
│   │   └── service.py            # LLM service facade
│   ├── models/                   # MongoDB document models
│   │   └── __init__.py           # Pydantic models
│   ├── rag/                      # RAG (Retrieval-Augmented Generation)
│   │   └── service.py            # RAG implementation
│   ├── search/                   # Search infrastructure
│   │   ├── bm25.py               # Keyword search
│   │   ├── embeddings.py         # Vector embeddings
│   │   ├── hybrid.py             # Hybrid search fusion
│   │   └── vector_store.py       # Vector database
│   ├── services/                 # Business logic services
│   │   ├── amendments.py         # Amendment tracking
│   │   ├── consumer.py           # Consumer-facing services
│   │   ├── corpus.py             # Corpus management
│   │   ├── evidence.py           # Evidence processing
│   │   ├── findings.py           # Standards findings
│   │   ├── graph.py              # Knowledge graph
│   │   ├── product_understanding.py  # Product analysis
│   │   ├── regulatory.py         # Regulatory status
│   │   ├── serializers.py        # Data serialization
│   │   └── standard_discovery.py # Standard matching
│   └── schemas/                  # API schemas
│       └── models.py             # Request/response models
├── tests/                        # Test suite (274 tests)
└── requirements.txt              # Python dependencies
```

---

## 🔌 **API ARCHITECTURE**

### **FastAPI Application Setup** (`main.py`)
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import health, products, evidence, chat

app = FastAPI(title="BIS Standards Intelligence API")
app.add_middleware(CORSMiddleware)
app.include_router(health.router)
app.include_router(products.router, prefix="/api/products")
app.include_router(evidence.router, prefix="/api/evidence")
app.include_router(chat.router, prefix="/api/chat")
```

### **8 Main API Endpoints**

1. **Health API** (`/api/health`)
   - System status and metrics
   - Database connectivity
   - LLM provider status
   - Corpus statistics

2. **Products API** (`/api/products`)
   - `POST /analyze` - Analyze product description
   - `GET /{id}` - Get product profile
   - `POST /{id}/discover-standards` - Find applicable standards
   - `POST /{id}/compliance/analyze` - Run gap analysis

3. **Standards API** (`/api/standards`)
   - `GET /` - List standards with filters
   - `GET /{id}` - Get standard details
   - `GET /{id}/requirements` - Get requirements
   - `GET /{id}/findings` - Get clause-level findings

4. **Evidence API** (`/api/evidence`)
   - `POST /upload` - Upload evidence files
   - `GET /{id}` - Get evidence details
   - `DELETE /{id}` - Delete evidence

5. **Certification API** (`/api/certification`)
   - `GET /schemes` - List BIS schemes
   - `GET /{id}/process` - Get certification process

6. **Hallmarking API** (`/api/hallmarking`)
   - `GET /consumer-guide` - Consumer guidance
   - `GET /centres` - Testing centres

7. **Chat API** (`/api/chat`)
   - `POST /message` - AI assistant chat
   - `GET /health` - Chat system status

8. **RAG API** (`/api/rag`)
   - `POST /query` - Knowledge base queries

---

## 🗄️ **DATABASE ARCHITECTURE**

### **MongoDB Connection** (`db/mongo.py`)
```python
from pymongo import MongoClient
from app.core.config import settings

client = MongoClient(
    settings.mongo_uri,
    serverSelectionTimeoutMS=settings.mongo_timeout_ms
)
db = client[settings.mongo_db_name]
```

### **9 Core Collections**

1. **standards** - Standard documents
   ```python
   {
       "_id": ObjectId,
       "id": "IS-302-2023", 
       "title": "Electric Irons - Safety Requirements",
       "document_type": "is_standard",
       "is_verified": True,
       "category": "electrical_appliances"
   }
   ```

2. **standard_clauses** - Clause-level chunks
   ```python
   {
       "_id": ObjectId,
       "chunk_id": "IS-302-2023:clause_5_2_1",
       "standard_id": "IS-302-2023",
       "text": "The appliance shall be tested...",
       "clause_number": "5.2.1",
       "page_number": 15
   }
   ```

3. **compliance_requirements** - Structured requirements
   ```python
   {
       "_id": ObjectId,
       "requirement_id": "IS-302-2023:req_001",
       "standard_id": "IS-302-2023", 
       "text": "Insulation resistance test required",
       "type": "test",
       "mandatory": True
   }
   ```

4. **products** - Product profiles
   ```python
   {
       "_id": ObjectId,
       "product_id": "prod_123",
       "description": "Electric iron for household",
       "attributes": {
           "category": "electrical_appliances",
           "voltage": "230V",
           "materials": ["plastic", "metal"]
       },
       "standards_analysis": {...}
   }
   ```

### **Vector Collections**
- **vectors_standards** - Document embeddings (384-dim)
- **vectors_clauses** - Clause embeddings (384-dim)

---

## 🧠 **CORE SERVICES ARCHITECTURE**

### **1. Product Understanding Service** (`services/product_understanding.py`)
```python
class ProductUnderstandingService:
    def extract_attributes(self, description: str) -> ProductAttributes:
        """Extract structured attributes from product description"""
        # Uses NLP to identify:
        # - Category & subcategory
        # - Materials & components  
        # - Intended use
        # - Technical specifications
        
    def generate_interview_questions(self, product: Product) -> List[Question]:
        """Generate targeted questions to fill knowledge gaps"""
```

### **2. Standard Discovery Service** (`services/standard_discovery.py`)
```python
class StandardDiscoveryService:
    def discover_standards(self, product: Product) -> List[StandardMatch]:
        """Two-stage hybrid retrieval"""
        # Stage 1: Hybrid search
        candidates = self._hybrid_search(product)
        
        # Stage 2: Reranking  
        ranked = self._rerank_by_relevance(candidates, product)
        
        return ranked
        
    def _hybrid_search(self, product: Product) -> List[Standard]:
        """Combine vector + keyword search"""
        vector_results = self.vector_search.search(product.embedding)
        bm25_results = self.bm25_search.search(product.description) 
        
        # Fusion with weights: 60% vector + 30% BM25 + 10% metadata
        return self._fuse_results(vector_results, bm25_results)
```

### **3. Compliance Gap Analyzer** (`compliance/gap_analyzer.py`)
```python
class GapAnalyzer:
    def analyze_compliance(self, product: Product, standards: List[Standard]) -> ComplianceReport:
        """Requirement-by-requirement gap analysis"""
        gaps = []
        
        for standard in standards:
            requirements = self._extract_requirements(standard)
            for req in requirements:
                status = self._assess_requirement(req, product.evidence)
                if status.has_gap:
                    gaps.append(status)
                    
        return ComplianceReport(gaps=gaps, readiness_score=self._calculate_score(gaps))
```

### **4. RAG Service** (`rag/service.py`)
```python
class RAGService:
    def query(self, question: str, context: Optional[str] = None) -> RAGResponse:
        """Retrieval-Augmented Generation with Evidence Shield"""
        
        # Step 1: Retrieve relevant chunks
        chunks = self.retriever.retrieve(question, top_k=8)
        
        # Step 2: Generate answer with LLM
        answer = self.llm.generate(question, chunks)
        
        # Step 3: Evidence Shield validation
        validated_answer = self.evidence_shield.validate(answer, chunks)
        
        return RAGResponse(
            answer=validated_answer.text,
            sources=chunks,
            claims_verified=validated_answer.verified_claims
        )
```

### **5. LLM Service** (`llm/service.py`)
```python
class LLMService:
    def __init__(self):
        self.provider = self._build_provider()  # Auto-detect from config
        
    def text(self, system: str, prompt: str, **kwargs) -> Optional[str]:
        """Generate text response"""
        if not self.available:
            return None
            
        result = self.provider.generate(system, prompt, **kwargs)
        return result.text if result.ok else None
        
    def structured(self, system: str, prompt: str, model: Type[T]) -> Optional[T]:
        """Generate structured JSON response"""
        # JSON generation with validation and retry logic
```

---

## 🔍 **SEARCH ARCHITECTURE**

### **Hybrid Search Pipeline** (`search/hybrid.py`)
```python
class HybridSearchService:
    def __init__(self):
        self.vector_store = get_vector_store()
        self.bm25_index = BM25Index()
        self.reranker = get_reranker()
        
    def search(self, query: str, filters: Dict = None) -> List[SearchResult]:
        # Vector search (semantic similarity)
        vector_results = self.vector_store.similarity_search(
            query, top_k=50, filters=filters
        )
        
        # BM25 search (keyword matching)
        bm25_results = self.bm25_index.search(query, top_k=50)
        
        # Fusion with configurable weights
        fused = self._reciprocal_rank_fusion(
            vector_results, bm25_results,
            weights=(settings.weight_semantic, settings.weight_bm25)
        )
        
        # Reranking for final precision
        if self.reranker.available:
            fused = self.reranker.rerank(query, fused)
            
        return fused[:20]  # Return top 20
```

### **Vector Store** (`search/vector_store.py`)
```python
class MongoVectorStore:
    def similarity_search(self, query: str, top_k: int = 10) -> List[Document]:
        # Generate embedding
        embedding = self.embedding_model.encode(query)
        
        # Atlas Vector Search if available
        if self._atlas_search_available():
            return self._atlas_vector_search(embedding, top_k)
        
        # Fallback to brute-force cosine similarity
        return self._brute_force_search(embedding, top_k)
        
    def _atlas_vector_search(self, embedding: List[float], top_k: int):
        pipeline = [
            {
                "$vectorSearch": {
                    "index": "vector_index",
                    "path": "embedding",
                    "queryVector": embedding,
                    "numCandidates": top_k * 10,
                    "limit": top_k
                }
            }
        ]
        return list(self.collection.aggregate(pipeline))
```

---

## 🛡️ **ANTI-HALLUCINATION SYSTEM**

### **Evidence Shield** (`rag/service.py`)
```python
class EvidenceShield:
    def validate(self, answer: str, source_chunks: List[Chunk]) -> ValidatedAnswer:
        """Validate every claim against retrieved evidence"""
        
        claims = self._extract_claims(answer)
        verified_claims = []
        rejected_claims = []
        
        for claim in claims:
            supporting_chunks = self._find_supporting_evidence(claim, source_chunks)
            
            if self._has_sufficient_support(claim, supporting_chunks):
                verified_claims.append(VerifiedClaim(
                    text=claim.text,
                    source_chunk_ids=[c.chunk_id for c in supporting_chunks]
                ))
            else:
                rejected_claims.append(RejectedClaim(
                    text=claim.text,
                    reason="Insufficient evidence in retrieved chunks"
                ))
                
        return ValidatedAnswer(
            verified_claims=verified_claims,
            rejected_claims=rejected_claims,
            final_text=self._rebuild_answer(verified_claims)
        )
```

### **5 Backend Controls**
1. **Closed Candidate List** - Only existing standard IDs accepted
2. **Evidence Shield** - All claims validated against sources  
3. **Structured Regulatory** - QCO data from database only
4. **Closed Vocabulary** - Fixed compliance status options
5. **Deterministic Diffs** - Text comparison, not AI generation

---

## 📊 **DATA PROCESSING PIPELINE**

### **Document Ingestion** (`ingestion/pipeline.py`)
```python
class IngestionPipeline:
    def process_document(self, pdf_path: str) -> ProcessingResult:
        # Step 1: PDF parsing
        document = self.pdf_parser.parse(pdf_path)
        
        # Step 2: Clause extraction  
        clauses = self.clause_extractor.extract(document)
        
        # Step 3: Requirement identification
        requirements = self.requirement_extractor.extract(clauses)
        
        # Step 4: Embedding generation
        embeddings = self.embedding_service.generate_embeddings(clauses)
        
        # Step 5: Database storage
        self._store_processed_data(document, clauses, requirements, embeddings)
        
        return ProcessingResult(
            clauses_extracted=len(clauses),
            requirements_found=len(requirements),
            embeddings_generated=len(embeddings)
        )
```

### **Embedding Pipeline** (`search/embeddings.py`)
```python
class EmbeddingService:
    def __init__(self):
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        
    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate 384-dimensional embeddings"""
        return self.model.encode(texts, normalize_embeddings=True).tolist()
        
    def generate_query_embedding(self, query: str) -> List[float]:
        """Generate embedding for search query"""
        return self.model.encode(query, normalize_embeddings=True).tolist()
```

---

## ⚙️ **CONFIGURATION SYSTEM**

### **Settings** (`core/config.py`)
```python
class Settings(BaseSettings):
    # Database
    mongo_uri: str = Field(alias="MONGO_URI")
    mongo_db_name: str = Field(default="sih26107")
    
    # LLM
    llm_provider: str = Field(default="auto")  # auto, gemini, openai, anthropic
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    
    # Search weights
    weight_semantic: float = Field(default=0.60)
    weight_bm25: float = Field(default=0.30) 
    weight_metadata: float = Field(default=0.10)
    
    # Retrieval
    clause_top_k: int = Field(default=8)
    discovery_candidate_limit: int = Field(default=8)
    
    class Config:
        env_file = ".env"
```

---

## 🧪 **TESTING ARCHITECTURE**

### **Test Structure** (`tests/`)
```python
# API Tests
def test_product_analysis_endpoint():
    response = client.post("/api/products/analyze", json={
        "description": "Electric iron for household use"
    })
    assert response.status_code == 200
    assert "product_id" in response.json()

# Service Tests  
def test_standard_discovery_service():
    service = StandardDiscoveryService()
    product = Product(description="Pressure cooker")
    
    matches = service.discover_standards(product)
    
    assert len(matches) > 0
    assert matches[0].relevance in ["HIGH", "MEDIUM", "LOW"]

# Guardrail Tests
def test_evidence_shield_prevents_hallucinations():
    answer = "IS-999999 requires impossible test"  # Non-existent standard
    chunks = [...]  # Real retrieved chunks
    
    validated = evidence_shield.validate(answer, chunks)
    
    assert len(validated.rejected_claims) > 0
    assert "IS-999999" not in validated.final_text
```

---

## 🚀 **DEPLOYMENT & OPERATIONS**

### **Development Setup**
```bash
# Environment setup
cd backend
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt

# Configuration
cp .env.example .env
# Edit .env with your MongoDB URI and API keys

# Run development server
uvicorn app.main:app --reload --port 8000

# API documentation available at:
# http://localhost:8000/docs (Swagger)
# http://localhost:8000/redoc (ReDoc)
```

### **Production Deployment** (Render)
```dockerfile
# Dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "$PORT"]
```

### **Health Monitoring**
```python
# Built-in health endpoint provides:
{
    "status": "ok",
    "database": {"backend": "mongodb", "connected": true},
    "llm": {"available": true, "provider": "gemini"},
    "retrieval": {"vector_backend": "mongodb_atlas"},
    "corpus": {"standards": 1247, "verified": 1247}
}
```

---

## 🔄 **REQUEST/RESPONSE FLOW**

### **Complete Request Lifecycle**
```
1. HTTP Request → FastAPI Router
2. Request Validation → Pydantic Models  
3. Dependency Injection → Database Session
4. Service Layer → Business Logic
5. Database Operations → MongoDB
6. Response Serialization → JSON
7. HTTP Response → Client
```

### **Example: Product Analysis Flow**
```python
# 1. API Endpoint
@router.post("/analyze")
async def analyze_product(request: ProductAnalyzeRequest):
    
# 2. Service Layer
service = ProductUnderstandingService()
product = service.analyze(request.description)

# 3. Database Storage  
product_id = products_repo.create(product)

# 4. Background Processing
discovery_service = StandardDiscoveryService()
matches = discovery_service.discover_standards(product)

# 5. Response
return ProductAnalyzeResponse(
    product_id=product_id,
    attributes=product.attributes,
    suggested_standards=matches
)
```

---

This backend guide covers all the technical details your development team needs to understand the architecture, work with the codebase, and maintain the system. Each service is designed to be modular and testable, following FastAPI and Python best practices.