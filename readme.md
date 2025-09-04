# Quotation Microservice

A FastAPI-based microservice for generating quotations with email drafts using Google's Gemini AI.

## Features

- Generate quotations with calculated line items and grand totals
- Create professional email drafts in English or Arabic
- OpenAPI documentation available at `/docs`
- Health check endpoint
- Mock mode for local development without API keys

## API Endpoints

- `GET /` - Service status
- `GET /health` - Health check
- `POST /quote` - Generate a quotation

## Request Format

```json
{
  "client": {
    "name": "Company Name",
    "contact": "email@company.com",
    "lang": "en"
  },
  "currency": "SAR",
  "items": [
    {
      "sku": "PRODUCT-SKU",
      "qty": 10,
      "unit_cost": 100.0,
      "margin_pct": 20.0
    }
  ],
  "delivery_terms": "Delivery terms",
  "notes": "Additional notes"
}