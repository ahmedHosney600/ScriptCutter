import re

def parse_script(raw_text):
    """
    Scans a raw string and extracts text wrapped in triple quotes.
    Returns a list of clean string segments.
    """
    # re.DOTALL allows the regex to match across multiple line breaks
    matches = re.findall(r'"""(.*?)"""', raw_text, re.DOTALL)
    
    # Strip empty spaces and ignore fully empty blocks
    segments = [match.strip() for match in matches if match.strip()]
    
    return segments

def parse_script_with_spans(raw_text):
    """
    Scans a raw string and extracts text wrapped in triple quotes.
    Returns a list of tuples: (clean_segment, span_start, span_end).
    The span includes the triple quotes.
    """
    matches = list(re.finditer(r'"""(.*?)"""', raw_text, re.DOTALL))
    
    results = []
    for match in matches:
        content = match.group(1)
        if content.strip():
            results.append((content.strip(), match.start(), match.end()))
            
    return results