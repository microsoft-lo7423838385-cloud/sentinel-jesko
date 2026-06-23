
import base64
from faker import Faker
import random
import hashlib

# Initialize Faker to generate fake data
fake = Faker()

# --- New Dynamic Data Lists ---
JOB_TITLES = [
    "Project Manager", "Account Executive", "Senior Developer", "Marketing Specialist",
    "Operations Coordinator", "Product Owner", "Data Analyst", "HR Manager",
    "Customer Success Manager", "Lead Designer", "Business Development Rep"
]

CITIES = [
    "New York", "London", "Tokyo", "Paris", "Singapore", "Dubai", "Hong Kong",
    "Sydney", "Los Angeles", "Chicago", "Toronto", "Berlin", "Moscow"
]

POSITIVE_ADJECTIVES = [
    "important", "valuable", "critical", "essential", "key", "significant", "crucial"
]

# --- New Generator Functions ---
def generate_random_job_title():
    return random.choice(JOB_TITLES)

def generate_random_city():
    return random.choice(CITIES)

def generate_random_md5():
    """Generates a random MD5 hash."""
    return hashlib.md5(str(random.random()).encode()).hexdigest()

def generate_fake_company_data():
    """Generates a dictionary of fake company data."""
    company_name = fake.company()
    return {
        "company_name": company_name,
        "address": fake.address(),
        "phone_number": fake.phone_number(),
    }

def generate_fake_person_data():
    """Generates a dictionary of a fake person's data, including a realistic company email."""
    first_name = fake.first_name()
    last_name = fake.last_name()
    full_name = f"{first_name} {last_name}"
    
    # Create a sanitized company name for the email domain
    company_name = fake.company().replace(" ", "").replace(",", "").lower()
    company_domain = f"{company_name}.com"
    
    email = f"{first_name.lower()}.{last_name.lower()}@{company_domain}"
    
    return {
        "full_name": full_name,
        "email": email,
        "email_with_name": f'"{full_name}" <{email}>'
    }

def generate_random_path(length=125):
    """Generates a random, URL-safe, base64-encoded path string."""
    random_bytes = random.getrandbits(length * 8).to_bytes(length, byteorder='big')
    base64_encoded = base64.b64encode(random_bytes).decode('utf-8')
    safe_path = base64_encoded.replace('+', '-').replace('/', '_').rstrip('=')
    return safe_path

def obfuscate_attachment(content):
    pass
