from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import os
import logging
from datetime import datetime
import uvicorn

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Quotation Microservice",
    description="A microservice for generating quotations with email drafts",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Pydantic models
class Client(BaseModel):
    name: str = Field(..., description="Client company name")
    contact: str = Field(..., description="Client contact email")
    lang: str = Field(..., description="Language code (en/ar)")

class Item(BaseModel):
    sku: str = Field(..., description="Stock keeping unit")
    qty: int = Field(..., gt=0, description="Quantity")
    unit_cost: float = Field(..., gt=0, description="Unit cost")
    margin_pct: float = Field(..., ge=0, le=100, description="Margin percentage")

class QuoteRequest(BaseModel):
    client: Client
    currency: str = Field(..., description="Currency code (e.g., SAR, USD)")
    items: List[Item] = Field(..., min_items=1, description="List of items")
    delivery_terms: str = Field(..., description="Delivery terms")
    notes: Optional[str] = Field(None, description="Additional notes")

class LineItem(BaseModel):
    sku: str
    qty: int
    unit_cost: float
    margin_pct: float
    line_total: float

class QuoteResponse(BaseModel):
    quote_id: str
    client: Client
    currency: str
    line_items: List[LineItem]
    grand_total: float
    delivery_terms: str
    notes: Optional[str]
    email_draft: str
    generated_at: str

# Gemini client (with mock fallback)
class LLMService:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.mock_mode = not self.api_key
        
        if not self.mock_mode:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                self.model = genai.GenerativeModel('gemini-pro')
            except ImportError:
                logger.warning("Google Generative AI package not installed, using mock mode")
                self.mock_mode = True
        
        if self.mock_mode:
            logger.info("Running in mock mode - no Gemini API key provided")

    async def generate_email_draft(self, quote_data: Dict[str, Any]) -> str:
        if self.mock_mode:
            return self._generate_mock_email(quote_data)
        
        try:
            # Prepare the prompt based on language
            lang = quote_data["client"]["lang"]
            prompt = self._build_prompt(quote_data, lang)
            
            response = self.model.generate_content(prompt)
            return response.text.strip()
            
        except Exception as e:
            logger.error(f"Error generating email with Gemini: {e}")
            return self._generate_mock_email(quote_data)

    def _build_prompt(self, quote_data: Dict[str, Any], lang: str) -> str:
        client_name = quote_data["client"]["name"]
        total = quote_data["grand_total"]
        currency = quote_data["currency"]
        delivery = quote_data["delivery_terms"]
        notes = quote_data.get("notes", "")
        
        if lang == "ar":
            prompt = f"""
            اكتب مسودة بريد إلكتروني باللغة العربية لعرض سعر احترافي للعميل {client_name}.
            المعلومات:
            - إجمالي المبلغ: {total} {currency}
            - شروط التسليم: {delivery}
            - ملاحظات إضافية: {notes}
            
            يجب أن يكون البريد مهذباً ومهنياً ويتضمن جميع التفاصيل المهمة.
            """
        else:
            prompt = f"""
            Write a professional quotation email draft in English for client {client_name}.
            Details:
            - Total amount: {total} {currency}
            - Delivery terms: {delivery}
            - Additional notes: {notes}
            
            The email should be polite, professional, and include all important details.
            """
        
        return prompt

    def _generate_mock_email(self, quote_data: Dict[str, Any]) -> str:
        client_name = quote_data["client"]["name"]
        contact = quote_data["client"]["contact"]
        total = quote_data["grand_total"]
        currency = quote_data["currency"]
        delivery = quote_data["delivery_terms"]
        notes = quote_data.get("notes", "")
        lang = quote_data["client"]["lang"]
        
        if lang == "ar":
            return f"""الموضوع: عرض سعر - {client_name}

عزيزي/عزيزتي {contact},

نتشرف بتقديم عرض السعر التالي:

إجمالي المبلغ: {total:,.2f} {currency}
شروط التسليم: {delivery}

{f"ملاحظات إضافية: {notes}" if notes else ""}

نأمل أن يحوز عرضنا على رضاكم، ونتطلع للعمل معكم.

مع أطيب التحيات،
فريق المبيعات"""
        else:
            return f"""Subject: Quotation - {client_name}

Dear {contact},

We are pleased to provide you with the following quotation:

Total Amount: {total:,.2f} {currency}
Delivery Terms: {delivery}

{f"Additional Notes: {notes}" if notes else ""}

We hope our proposal meets your requirements and look forward to working with you.

Best regards,
Sales Team"""

# Initialize LLM service
llm_service = LLMService()

# Business logic
class QuotationService:
    @staticmethod
    def calculate_line_total(item: Item) -> float:
        """Calculate line total: unit_cost × (1 + margin_pct%) × qty"""
        return item.unit_cost * (1 + item.margin_pct / 100) * item.qty
    
    @staticmethod
    def generate_quote_id() -> str:
        """Generate a unique quote ID"""
        from datetime import datetime
        return f"QT-{datetime.now().strftime('%Y%m%d%H%M%S')}"

# API endpoints
@app.get("/")
async def root():
    return {"message": "Quotation Microservice", "status": "running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.post("/quote", response_model=QuoteResponse)
async def create_quote(request: QuoteRequest):
    """
    Generate a quotation with calculated totals and email draft.
    
    - **client**: Client information including name, contact, and language preference
    - **currency**: Currency code (e.g., SAR, USD)
    - **items**: List of items with SKU, quantity, unit cost, and margin percentage
    - **delivery_terms**: Delivery terms and timeline
    - **notes**: Additional notes or specifications
    """
    try:
        # Generate quote ID
        quote_id = QuotationService.generate_quote_id()
        
        # Calculate line items
        line_items = []
        grand_total = 0.0
        
        for item in request.items:
            line_total = QuotationService.calculate_line_total(item)
            line_item = LineItem(
                sku=item.sku,
                qty=item.qty,
                unit_cost=item.unit_cost,
                margin_pct=item.margin_pct,
                line_total=line_total
            )
            line_items.append(line_item)
            grand_total += line_total
        
        # Prepare data for email generation
        quote_data = {
            "quote_id": quote_id,
            "client": request.client.dict(),
            "currency": request.currency,
            "grand_total": grand_total,
            "delivery_terms": request.delivery_terms,
            "notes": request.notes
        }
        
        # Generate email draft
        email_draft = await llm_service.generate_email_draft(quote_data)
        
        # Create response
        response = QuoteResponse(
            quote_id=quote_id,
            client=request.client,
            currency=request.currency,
            line_items=line_items,
            grand_total=grand_total,
            delivery_terms=request.delivery_terms,
            notes=request.notes,
            email_draft=email_draft,
            generated_at=datetime.now().isoformat()
        )
        
        logger.info(f"Quote generated successfully: {quote_id}")
        return response
        
    except Exception as e:
        logger.error(f"Error generating quote: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)