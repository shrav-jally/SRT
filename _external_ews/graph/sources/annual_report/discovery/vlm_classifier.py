import json
from pathlib import Path

from ..vlm_extractor import _call_vlm_with_images, render_page_images
from .models import StatementType

def classify_pages_with_vlm(
    pdf_path: Path,
    page_numbers: list[int],
    dpi: int = 150
) -> dict[int, StatementType | None]:
    """Uses the configured VLM to classify corrupted or image-based pages.
    
    Returns a dict mapping page_number to the identified StatementType (or None).
    """
    if not page_numbers:
        return {}

    results: dict[int, StatementType | None] = {}
    
    # We use a very strict JSON schema prompt to classify the page
    sys_prompt = (
        "You are a financial document classification AI. Your task is to analyze the provided image of a page "
        "from an Annual Report and classify it into exactly ONE of the following categories:\n"
        "1. standalone_balance_sheet\n"
        "2. standalone_profit_and_loss\n"
        "3. standalone_cash_flow\n"
        "4. consolidated_balance_sheet\n"
        "5. consolidated_profit_and_loss\n"
        "6. consolidated_cash_flow\n"
        "7. none\n\n"
        "If it is a Balance Sheet, Profit & Loss, or Cash Flow Statement, you MUST determine if it is "
        "'Standalone' (Company only) or 'Consolidated' (Group). "
        "If it is none of these (e.g. it is an auditor report, a notes page, or index), output 'none'.\n\n"
        "Respond STRICTLY with valid JSON in the following format:\n"
        "{\n"
        '  "classification": "<one of the 7 exact strings above>"\n'
        "}"
    )

    for page_num in page_numbers:
        try:
            print(f"  [Discovery] Running VLM classification on corrupted page {page_num}...")
            # Render the page to an image
            images = render_page_images(pdf_path, [page_num], dpi=dpi)
            
            # Call VLM with the rendered image
            response_text = _call_vlm_with_images(
                prompt="Classify this page based on the system instructions.",
                images=images,
                system_prompt=sys_prompt,
                json_schema={
                    "type": "object",
                    "properties": {
                        "classification": {
                            "type": "string",
                            "enum": [
                                "standalone_balance_sheet",
                                "standalone_profit_and_loss",
                                "standalone_cash_flow",
                                "consolidated_balance_sheet",
                                "consolidated_profit_and_loss",
                                "consolidated_cash_flow",
                                "none"
                            ]
                        }
                    },
                    "required": ["classification"]
                }
            )
            
            # Parse the response (handles markdown fences if present)
            from ..vlm_extractor import _extract_json_from_response
            data = _extract_json_from_response(response_text)
            if not data:
                data = {}
            cls_str = data.get("classification", "none")
            
            if cls_str != "none":
                results[page_num] = StatementType(cls_str)
                print(f"  [Discovery] VLM classified page {page_num} as: {cls_str}")
            else:
                results[page_num] = None
                print(f"  [Discovery] VLM classified page {page_num} as: none")
                
        except Exception as e:
            print(f"  [Discovery] VLM classification failed for page {page_num}: {e}")
            results[page_num] = None

    return results
