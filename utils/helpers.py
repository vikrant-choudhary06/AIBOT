import re

# Common Hinglish stopwords/words
HINGLISH_WORDS = {
    "kya", "hai", "kaise", "bhai", "yaar", "tha", "raha", "hoga", "tum", "aap",
    "aur", "toh", "nhi", "nahi", "kar", "kuch", "ko", "se", "ek", "haan",
    "kiya", "karna", "kr", "chal", "rha", "rhi", "he", "krna", "kab", "kaha",
    "kahan", "ab", "tak", "gaya", "gayi", "gya", "baat", "karo", "krlo", "aaj",
    "kal", "din", "log", "kam", "kuchh", "hota", "hoti", "hua", "hue", "naam",
    "kya-kya", "thik", "theek", "sahi", "galat", "khel", "paas", "dur", "saath"
}

def clean_text(text: str, self_username: str = None) -> str:
    """
    Cleans raw text by stripping out bot mentions/tags and normalizing whitespace.
    """
    if not text:
        return ""
    
    # Strip username mentions (e.g., @my_username)
    if self_username:
        text = re.sub(rf"(?i)@{self_username}\b", "", text)
    
    # Strip other standard user mentions to avoid confusing the AI
    text = re.sub(r"@\w+", "", text)
    
    # Normalize whitespaces
    text = re.sub(r"\s+", " ", text).strip()
    return text

def is_hinglish(text: str) -> bool:
    """
    Heuristic check to determine if a message is written in Hinglish.
    Checks if words in the text match a list of common Hinglish vocabulary.
    """
    if not text:
        return False
    
    # Convert to lowercase and extract words
    words = re.findall(r"\b[a-z']+\b", text.lower())
    if not words:
        return False
    
    match_count = sum(1 for word in words if word in HINGLISH_WORDS)
    ratio = match_count / len(words)
    
    # If 20% or more of words are Hinglish vocabulary, or at least 2 words match
    return ratio >= 0.20 or match_count >= 2

def detect_tone(text: str) -> str:
    """
    Simple heuristic-based tone detector to adapt response style.
    Returns: 'roast', 'humorous', 'question', 'angry', 'casual'
    """
    if not text:
        return "casual"
        
    text_lower = text.lower()
    
    # Roasting/abusive markers (basic filtering / tone match)
    roast_markers = ["lol", "noob", "bot", "lmao", "roast", "fail", "joke", "chutiya", "bakwas", "loser", "fucker"]
    if any(m in text_lower for m in roast_markers):
        return "playful_roast"
        
    # Question markers
    if "?" in text or any(q in text_lower for q in ["how", "why", "what", "who", "when", "where", "kya", "kab", "kaha"]):
        return "inquisitive"
        
    # Anger / Exclamation markers
    if "!" in text and any(a in text_lower for a in ["wtf", "stop", "hate", "irritate", "fuck", "gussa"]):
        return "annoyed"

    return "casual"

def is_looping(text: str) -> bool:
    """
    Checks if the generated text is looping internally (repeating words or phrases).
    """
    if not text:
        return False
        
    clean_text_val = text.strip().lower()
    words = clean_text_val.split()
    if len(words) > 4:
        # Check if the text consists of the same word repeated
        if len(set(words)) == 1:
            return True
        # Check if a pair of words is repeated constantly
        pairs = [" ".join(words[i:i+2]) for i in range(len(words)-1)]
        if len(pairs) > 3 and len(set(pairs)) <= len(pairs) // 3:
            return True
            
    return False

def is_duplicate_response(text: str, history: list[str], threshold: int = 3) -> bool:
    """
    Checks if the completed text is a duplicate of a recent past response.
    """
    if not text or not history:
        return False
    clean_reply = text.strip().lower()
    # Check direct match with past history
    for past_reply in history[-threshold:]:
        if clean_reply == past_reply.strip().lower():
            return True
    return False
