"""DocAI Pipelines — independently callable document analysis pipelines."""

from pipelines.year_over_year import YearOverYearPipeline
from pipelines.pta import PTAPipeline
from pipelines.summarizer import SummarizerPipeline
from pipelines.donor_intent import DonorIntentPipeline
from pipelines.general import GeneralPipeline

PIPELINES = {
    "general": GeneralPipeline,
    "year_over_year": YearOverYearPipeline,
    "pta": PTAPipeline,
    "summarizer": SummarizerPipeline,
    "donor_intent": DonorIntentPipeline,
}

PIPELINE_LABELS = {
    "general": "General Q&A (any docs, any question)",
    "year_over_year": "Year-over-Year Financial Comparison",
    "pta": "Pattern / Trend / Anomaly Detection",
    "summarizer": "Document Summarizer",
    "donor_intent": "Donor Intent Extraction (OCR)",
}
