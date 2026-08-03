# Early Warning System

Agentic corporate governance Early Warning System for AML-oriented risk checks.

The project is organized around two reusable LangGraph workflows:

- `ews_analysis`: analyzes annual reports and other sources to produce governance check scores.
- `report_downloader`: downloads previous annual reports from NSE, BSE, company websites, or public sources and packages them as a ZIP.
- `ui`: lightweight Streamlit demo UI for stakeholders and integration discussions.

Score convention:

- `1`: harmful signal found
- `0`: checked and harm-free
- `null`: insufficient evidence / not verified

## Demo UI

Run the demo UI with:

```bash
streamlit run ui/streamlit_app.py
```

The UI currently falls back to sample data because the workflow nodes are scaffolded placeholders.
