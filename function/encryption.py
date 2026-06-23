
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from Crypto.Random import get_random_bytes
import base64
import hashlib
import random

def encrypt_attachment(content, password='default', random_level=-1, strictness=0, line_length=76):
    """
    Encrypts attachment content using AES with settings inspired by Project 1's config.

    Args:
        content (bytes): The content of the attachment to encrypt.
        password (str): The password for encryption.
        random_level (int): The randomness level (1-15, or -1 for random).
        strictness (int): The strictness level (0 for low, 1 for high).
        line_length (int): The length of lines for the output.

    Returns:
        str: The base64 encoded encrypted content.
    """
    if password == 'default':
        password = 'your_default_password'  # It's better to have a real default password

    # Derive a key from the password
    if strictness == 1:
        # Use SHA-256 for a more secure key derivation
        key = hashlib.sha256(password.encode()).digest()
    else:
        # Use MD5 for a less secure, but faster key derivation
        key = hashlib.md5(password.encode()).digest()

    # Create a new AES cipher
    cipher = AES.new(key, AES.MODE_CBC)
    
    # Pad the content and encrypt it
    ciphertext = cipher.encrypt(pad(content, AES.block_size))

    # Add randomness if requested
    if random_level != 0:
        if random_level == -1:
            random_level = random.randint(1, 15)
        
        # Add random bytes to the ciphertext
        for _ in range(random_level):
            random_data = get_random_bytes(16)
            ciphertext += random_data

    # Base64 encode the result
    encoded_ciphertext = base64.b64encode(cipher.iv + ciphertext).decode('utf-8')

    # Format the output with specified line length
    if line_length > 0:
        return '\n'.join([encoded_ciphertext[i:i+line_length] for i in range(0, len(encoded_ciphertext), line_length)])
    else:
        return encoded_ciphertext
