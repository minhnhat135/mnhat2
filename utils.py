import random
import string

def generate_random_string(length=8):
    """Generates a random string of characters."""
    letters = string.ascii_lowercase
    return ''.join(random.choice(letters) for _ in range(length))

def random_email():
    """Generates a random email address."""
    prefix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=random.randint(8, 15)))
    domain = ''.join(random.choices(string.ascii_lowercase, k=random.randint(5, 10)))
    return f"{prefix}@{domain}.com"

def random_birth_day():
    """Generates a random day for birthday (1-28)."""
    return str(random.randint(1, 28)).zfill(2)

def random_birth_month():
    """Generates a random month for birthday (1-12)."""
    return str(random.randint(1, 12)).zfill(2)

def random_birth_year():
    """Generates a random year for birthday (1970-2005)."""
    return str(random.randint(1970, 2005))

def random_user_agent():
    """Generates a random realistic User-Agent string."""
    chrome_major = random.randint(100, 125)
    chrome_build = random.randint(0, 6500)
    chrome_patch = random.randint(0, 250)
    return f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_major}.0.{chrome_build}.{chrome_patch} Safari/537.36"
