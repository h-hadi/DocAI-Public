"""Prompt templates for each document analysis use case."""

SYSTEM_PROMPT = """You are a document analysis assistant. \
You analyze documents and provide structured insights including summaries, \
statistics, patterns, trends, and anomalies. Always be precise with numbers \
and cite specific documents when making claims. Format your output in clean \
Markdown with tables where appropriate."""


# ---------------------------------------------------------------------------
# Use-case templates
# ---------------------------------------------------------------------------

FINANCIAL_COMPARISON = """Analyze the following financial documents and provide:

1. **Year-over-Year Comparison Table**: For each financial metric found,
   show the value for each year/period side by side, with absolute and % change.
2. **Key Trends**: Identify the 3-5 most significant financial trends.
3. **Anomalies**: Flag any unusual changes (>20% YoY change) with explanation.
4. **Summary**: 2-3 paragraph executive summary of the financial picture.

Documents:
{content}

Additional context from vector store (most relevant prior indexed content):
{context}

User instruction: {instruction}"""


PTA_DETECTION = """Analyze the following documents for patterns, trends, and anomalies:

1. **Patterns**: Recurring themes, repeated values, consistent behaviors.
2. **Trends**: Directional changes over time — increasing, decreasing, cyclical.
3. **Anomalies**: Outliers, unexpected values, breaks from established patterns.
4. **Statistical Summary**: Key metrics with mean, median, range where applicable.
5. **Cross-Document Correlations**: Relationships between data in different files.

Documents:
{content}

Additional context from vector store:
{context}

User instruction: {instruction}"""


SUMMARIZATION = """Summarize the following documents:

For each document:
1. **Title/Source**: Document name
2. **Key Points**: 3-5 bullet points of the most important information
3. **Notable Data**: Any significant numbers, dates, or facts

Then provide:
4. **Cross-Document Summary**: A unified 2-3 paragraph synthesis
5. **Common Themes**: Themes appearing across multiple documents

Documents:
{content}

Additional context from vector store:
{context}

User instruction: {instruction}"""


DONOR_INTENT = """Analyze the following historical gift correspondence to extract donor intent:

For each document/letter:
1. **Donor**: Name and identifying information
2. **Gift Description**: What was given or pledged
3. **Stated Intent**: Direct quotes showing the donor's wishes
4. **Implied Intent**: Contextual clues about the donor's purpose
5. **Restrictions**: Any conditions or restrictions on the gift
6. **Time Period**: When the correspondence occurred

Then provide:
7. **Intent Summary**: Overall synthesis of the donor's charitable intent
8. **Confidence Level**: How clear is the intent (High/Medium/Low) with reasoning

Documents:
{content}

Additional context from vector store:
{context}

User instruction: {instruction}"""


GENERAL = """Analyze the following documents based on the user's instruction.
Provide structured output with:
1. Key findings
2. Relevant statistics and data points
3. Summary

Documents:
{content}

Additional context from vector store:
{context}

User instruction: {instruction}"""


# ---------------------------------------------------------------------------
# Template selection
# ---------------------------------------------------------------------------

TEMPLATE_MAP = {
    "financial": FINANCIAL_COMPARISON,
    "compare": FINANCIAL_COMPARISON,
    "year-over-year": FINANCIAL_COMPARISON,
    "yoy": FINANCIAL_COMPARISON,
    "revenue": FINANCIAL_COMPARISON,
    "budget": FINANCIAL_COMPARISON,
    "expense": FINANCIAL_COMPARISON,
    "pattern": PTA_DETECTION,
    "trend": PTA_DETECTION,
    "anomal": PTA_DETECTION,
    "detect": PTA_DETECTION,
    "outlier": PTA_DETECTION,
    "summarize": SUMMARIZATION,
    "summary": SUMMARIZATION,
    "overview": SUMMARIZATION,
    "donor": DONOR_INTENT,
    "intent": DONOR_INTENT,
    "gift": DONOR_INTENT,
    "correspondence": DONOR_INTENT,
    "pledge": DONOR_INTENT,
}


def select_template(instruction: str) -> str:
    """Auto-select prompt template based on instruction keywords."""
    instruction_lower = instruction.lower()
    for keyword, template in TEMPLATE_MAP.items():
        if keyword in instruction_lower:
            return template
    return GENERAL
