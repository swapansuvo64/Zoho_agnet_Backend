import re
from datetime import datetime, timedelta

def parse_date_to_zoho(val: str) -> str:
    """
    Normalizes a date string or keyword into Zoho Projects' expected 'MM-DD-YYYY' format.
    Supports:
      - Direct Keywords: 'today', 'tomorrow', 'yesterday', 'next day'
      - Relative Days: '2 days later', '3 days', '5 days after', 'two days later'
      - Weekdays: 'next monday', 'next week tuesday'
      - Next Month: 'next month'
      - Standard Formats: 'YYYY-MM-DD', 'MM/DD/YYYY', 'YYYY/MM/DD'
    """
    if not val:
        return val
        
    val_clean = str(val).lower().strip()
    
    # 1. Pre-process word numbers to digits
    word_to_digit = {
        "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
        "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10"
    }
    for word, digit in word_to_digit.items():
        val_clean = re.sub(r'\b' + word + r'\b', digit, val_clean)
    
    # 2. Direct Keywords
    if val_clean in ("today", "current"):
        return datetime.now().strftime("%m-%d-%Y")
    elif val_clean in ("tomorrow", "next day", "next-day"):
        return (datetime.now() + timedelta(days=1)).strftime("%m-%d-%Y")
    elif val_clean == "yesterday":
        return (datetime.now() - timedelta(days=1)).strftime("%m-%d-%Y")
    elif val_clean == "next month":
        now = datetime.now()
        # Fallback to ~30 days later
        return (now + timedelta(days=30)).strftime("%m-%d-%Y")
        
    # 3. X days later offset (e.g. "2 days later", "3 days", "5 days after")
    days_match = re.search(r'(\d+)\s*day[s]?\s*(later|after|from now)?', val_clean)
    if days_match:
        days_offset = int(days_match.group(1))
        return (datetime.now() + timedelta(days=days_offset)).strftime("%m-%d-%Y")
        
    # 4. Next week Monday / Next Monday / Next Tuesday etc.
    weekdays = {
        "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
        "friday": 4, "saturday": 5, "sunday": 6
    }
    
    for day_name, day_code in weekdays.items():
        if day_name in val_clean:
            now = datetime.now()
            days_ahead = day_code - now.weekday()
            if days_ahead <= 0: # Target day already happened this week or is today
                days_ahead += 7
            # If "next week" is specified and the day is later this week, we add another 7 days
            if "next week" in val_clean and (day_code > now.weekday()):
                days_ahead += 7
            return (now + timedelta(days=days_ahead)).strftime("%m-%d-%Y")
            
    # 5. Standard Date Formats (ISO YYYY-MM-DD)
    try:
        if "-" in val_clean and len(val_clean) == 10 and val_clean[4] == "-":
            dt = datetime.strptime(val_clean, "%Y-%m-%d")
            return dt.strftime("%m-%d-%Y")
    except Exception:
        pass
        
    # Check for slash formats MM/DD/YYYY or YYYY/MM/DD
    try:
        if "/" in val_clean:
            parts = val_clean.split("/")
            if len(parts) == 3:
                if len(parts[0]) == 4:
                    dt = datetime.strptime(val_clean, "%Y/%m/%d")
                    return dt.strftime("%m-%d-%Y")
                elif len(parts[2]) == 4:
                    dt = datetime.strptime(val_clean, "%m/%d/%Y")
                    return dt.strftime("%m-%d-%Y")
    except Exception:
        pass

    return val

def get_current_date_context() -> str:
    """
    Returns a formatted string representing the current date and time
    for use in LLM system prompts.
    """
    now = datetime.now()
    return (
        f"[Current Time Context]\n"
        f"- Current Timestamp: {now.strftime('%Y-%m-%d %I:%M:%S %p')}\n"
        f"- Today's Date: {now.strftime('%A, %B %d, %Y')} ({now.strftime('%m-%d-%Y')})\n"
        f"- Tomorrow's Date: {(now + timedelta(days=1)).strftime('%A, %B %d, %Y')} ({(now + timedelta(days=1)).strftime('%m-%d-%Y')})\n"
    )
