"""Verify imported Node.js scrypt passwords; Django upgrades them on next login."""
import hashlib
import secrets
from django.contrib.auth.hashers import BasePasswordHasher, mask_hash

class LegacyScryptHasher(BasePasswordHasher):
    algorithm = 'legacy_scrypt'
    def encode(self, password, salt):
        value = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1, dklen=64).hex()
        return self.algorithm + '$' + salt + '$' + value
    def verify(self, password, encoded):
        _, salt, _ = encoded.split('$', 2)
        return secrets.compare_digest(self.encode(password, salt), encoded)
    def safe_summary(self, encoded):
        _, salt, value = encoded.split('$', 2)
        return {'algorithm': self.algorithm, 'salt': mask_hash(salt), 'hash': mask_hash(value)}
    def must_update(self, encoded):
        return True
