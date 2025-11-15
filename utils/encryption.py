from cryptography.fernet import Fernet
import base64
import hashlib
from config import ENCRYPTION_KEY


class PasswordEncryption:
    """
    Класс для шифрования и расшифрования паролей.
    Использует симметричное шифрование Fernet (AES).
    """

    def __init__(self):
        """
        Инициализация шифровальщика.
        Создаёт ключ из ENCRYPTION_KEY.
        """
        # Преобразуем строку из config в ключ Fernet
        self.cipher = self._create_cipher()

    def _create_cipher(self):
        """
        Создать объект шифрования из ключа.

        Returns:
            Fernet: Объект для шифрования/расшифрования
        """
        # Fernet требует ключ длиной ровно 32 байта в base64
        # Используем хеш SHA-256 для получения стабильного ключа
        key_bytes = ENCRYPTION_KEY.encode('utf-8')
        hash_key = hashlib.sha256(key_bytes).digest()

        # Кодируем в base64 (требование Fernet)
        fernet_key = base64.urlsafe_b64encode(hash_key)

        return Fernet(fernet_key)

    def encrypt(self, password: str) -> str:
        """
        Зашифровать пароль.

        Args:
            password: Открытый пароль (строка)

        Returns:
            str: Зашифрованный пароль (строка в base64)

        Example:
            >>> encryptor = PasswordEncryption()
            >>> encrypted = encryptor.encrypt("my_password_123")
            >>> print(encrypted)
            'gAAAAABl...' (длинная строка)
        """
        try:
            # Преобразуем строку в байты
            password_bytes = password.encode('utf-8')

            # Шифруем
            encrypted_bytes = self.cipher.encrypt(password_bytes)

            # Преобразуем байты обратно в строку для хранения в БД
            encrypted_string = encrypted_bytes.decode('utf-8')

            return encrypted_string

        except Exception as e:
            print(f"❌ Ошибка шифрования: {e}")
            raise

    def decrypt(self, encrypted_password: str) -> str:
        """
        Расшифровать пароль.

        Args:
            encrypted_password: Зашифрованный пароль из БД

        Returns:
            str: Оригинальный пароль

        Example:
            >>> encryptor = PasswordEncryption()
            >>> decrypted = encryptor.decrypt('gAAAAABl...')
            >>> print(decrypted)
            'my_password_123'
        """
        try:
            # Преобразуем строку в байты
            encrypted_bytes = encrypted_password.encode('utf-8')

            # Расшифровываем
            decrypted_bytes = self.cipher.decrypt(encrypted_bytes)

            # Преобразуем байты в строку
            password = decrypted_bytes.decode('utf-8')

            return password

        except Exception as e:
            print(f"❌ Ошибка расшифрования: {e}")
            raise

    def is_valid_encrypted(self, encrypted_password: str) -> bool:
        """
        Проверить, является ли строка валидным зашифрованным паролем.

        Args:
            encrypted_password: Строка для проверки

        Returns:
            bool: True если валидно
        """
        try:
            self.decrypt(encrypted_password)
            return True
        except:
            return False


# Создаём глобальный экземпляр для удобного использования
encryptor = PasswordEncryption()


# Вспомогательные функции для быстрого доступа
def encrypt_password(password: str) -> str:
    """
    Быстрая функция для шифрования.

    Args:
        password: Открытый пароль

    Returns:
        str: Зашифрованный пароль
    """
    return encryptor.encrypt(password)


def decrypt_password(encrypted_password: str) -> str:
    """
    Быстрая функция для расшифрования.

    Args:
        encrypted_password: Зашифрованный пароль

    Returns:
        str: Открытый пароль
    """
    return encryptor.decrypt(encrypted_password)


# Тестирование (если запустить файл напрямую)
if __name__ == '__main__':
    print("🔐 Тестирование шифрования паролей\n")

    # Тестовый пароль
    original_password = "my_super_secret_password_123"
    print(f"Оригинальный пароль: {original_password}")

    # Шифруем
    encrypted = encrypt_password(original_password)
    print(f"Зашифрованный: {encrypted}")
    print(f"Длина зашифрованного: {len(encrypted)} символов\n")

    # Расшифровываем
    decrypted = decrypt_password(encrypted)
    print(f"Расшифрованный: {decrypted}")

    # Проверяем
    if original_password == decrypted:
        print("✅ Тест пройден! Пароли совпадают")
    else:
        print("❌ Тест провален! Пароли НЕ совпадают")