import imaplib
import email
from email.header import decode_header
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict
from config import IMAP_SETTINGS, CODE_REGEX, MAX_CODE_AGE_MINUTES, MAX_EMAILS_TO_CHECK


class EmailParser:
    """
    Класс для работы с почтой через IMAP.
    Подключается к почте, ищет коды в письмах.
    """

    def __init__(self, email_address: str, password: str, provider: str):
        """
        Инициализация парсера почты.

        Args:
            email_address: Email адрес (например, ivan@gmail.com)
            password: Пароль приложения
            provider: Провайдер (gmail, yandex, mail.ru, outlook)
        """
        self.email_address = email_address
        self.password = password
        self.provider = provider.lower()
        self.connection = None

    def connect(self) -> bool:
        """
        Подключиться к почтовому серверу.

        Returns:
            bool: True если подключение успешно
        """
        try:
            # Получаем настройки сервера из config
            if self.provider not in IMAP_SETTINGS:
                print(f"❌ Неизвестный провайдер: {self.provider}")
                return False

            server_info = IMAP_SETTINGS[self.provider]
            server = server_info['server']
            port = server_info['port']

            print(f"🔌 Подключаемся к {server}:{port}...")

            # Создаём SSL соединение с почтовым сервером
            self.connection = imaplib.IMAP4_SSL(server, port)

            # Авторизуемся
            self.connection.login(self.email_address, self.password)

            print(f"✅ Успешно подключились к {self.email_address}")
            return True

        except imaplib.IMAP4.error as e:
            print(f"❌ Ошибка авторизации IMAP: {e}")
            return False
        except Exception as e:
            print(f"❌ Ошибка подключения: {e}")
            return False

    def disconnect(self):
        """
        Отключиться от почтового сервера.
        """
        try:
            if self.connection:
                self.connection.logout()
                print("👋 Отключились от почты")
        except:
            pass

    def get_latest_emails(self, count: int = MAX_EMAILS_TO_CHECK) -> List[Dict]:
        """
        Получить последние N писем.

        Args:
            count: Количество писем (по умолчанию из config)

        Returns:
            List[Dict]: Список писем с полями: subject, from, date, body
        """
        try:
            # Выбираем папку INBOX (входящие)
            self.connection.select('INBOX')

            # Ищем все письма
            status, messages = self.connection.search(None, 'ALL')

            if status != 'OK':
                print("❌ Не удалось получить список писем")
                return []

            # messages[0] содержит строку с ID писем: b'1 2 3 4 5'
            email_ids = messages[0].split()

            if not email_ids:
                print("📭 В почте нет писем")
                return []

            # Берём последние N писем (ID от большего к меньшему)
            latest_ids = email_ids[-count:]
            latest_ids.reverse()  # От новых к старым

            emails = []

            for email_id in latest_ids:
                email_data = self._fetch_email(email_id)
                if email_data:
                    emails.append(email_data)

            print(f"📬 Получено {len(emails)} писем")
            return emails

        except Exception as e:
            print(f"❌ Ошибка получения писем: {e}")
            return []

    def _fetch_email(self, email_id: bytes) -> Optional[Dict]:
        """
        Получить данные одного письма.

        Args:
            email_id: ID письма

        Returns:
            Dict с полями письма или None
        """
        try:
            # Получаем письмо по ID
            status, msg_data = self.connection.fetch(email_id, '(RFC822)')

            if status != 'OK':
                return None

            # Парсим письмо
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            # Извлекаем заголовки
            subject = self._decode_header(msg['Subject'])
            from_email = msg.get('From', '')
            date_str = msg.get('Date', '')

            # Извлекаем тело письма
            body = self._get_email_body(msg)

            # Парсим дату
            email_date = self._parse_email_date(date_str)

            return {
                'subject': subject,
                'from': from_email,
                'date': email_date,
                'body': body
            }

        except Exception as e:
            print(f"❌ Ошибка парсинга письма {email_id}: {e}")
            return None

    def _decode_header(self, header: str) -> str:
        """
        Декодировать заголовок письма (может быть в разных кодировках).

        Args:
            header: Заголовок письма

        Returns:
            str: Декодированный текст
        """
        if not header:
            return ''

        try:
            decoded_parts = decode_header(header)
            decoded_str = ''

            for part, encoding in decoded_parts:
                if isinstance(part, bytes):
                    # Декодируем байты в строку
                    decoded_str += part.decode(encoding or 'utf-8', errors='ignore')
                else:
                    decoded_str += str(part)

            return decoded_str

        except Exception as e:
            print(f"❌ Ошибка декодирования заголовка: {e}")
            return str(header)

    def _get_email_body(self, msg) -> str:
        """
        Извлечь текст письма (тело).

        Args:
            msg: Объект письма

        Returns:
            str: Текст письма
        """
        body = ''

        try:
            # Письмо может быть многочастным (текст + HTML + вложения)
            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()

                    # Ищем текстовые части
                    if content_type == 'text/plain':
                        payload = part.get_payload(decode=True)
                        if payload:
                            charset = part.get_content_charset() or 'utf-8'
                            body += payload.decode(charset, errors='ignore')

                    elif content_type == 'text/html':
                        # HTML тоже может содержать код
                        payload = part.get_payload(decode=True)
                        if payload:
                            charset = part.get_content_charset() or 'utf-8'
                            html_text = payload.decode(charset, errors='ignore')
                            body += self._strip_html(html_text)
            else:
                # Простое письмо (не multipart)
                payload = msg.get_payload(decode=True)
                if payload:
                    charset = msg.get_content_charset() or 'utf-8'
                    body = payload.decode(charset, errors='ignore')

            return body

        except Exception as e:
            print(f"❌ Ошибка извлечения тела письма: {e}")
            return ''

    def _strip_html(self, html: str) -> str:
        """
        Убрать HTML теги из текста (простая версия).

        Args:
            html: HTML текст

        Returns:
            str: Текст без тегов
        """
        # Убираем теги <script> и <style> с содержимым
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)

        # Убираем все HTML теги
        text = re.sub(r'<[^>]+>', '', html)

        # Убираем лишние пробелы
        text = re.sub(r'\s+', ' ', text)

        return text.strip()

    def _parse_email_date(self, date_str: str) -> Optional[datetime]:
        """
        Парсить дату из заголовка письма.

        Args:
            date_str: Строка с датой

        Returns:
            datetime или None
        """
        try:
            # Используем встроенный парсер email
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(date_str)
        except:
            return None

    def find_codes_in_emails(self, emails: List[Dict]) -> List[Dict]:
        """
        Найти 2FA коды во всех письмах.
        УПРОЩЁННАЯ ВЕРСИЯ: ищем только в теме письма.

        Args:
            emails: Список писем из get_latest_emails()

        Returns:
            List[Dict]: Письма с найденными кодами
                        Формат: {'email': {...}, 'codes': ['123456', '7890']}
        """
        results = []

        for email_data in emails:
            # Проверяем возраст письма
            if not self._is_email_recent(email_data['date']):
                print(f"⏭️ Письмо слишком старое: {email_data['subject']}")
                continue

            # Ищем коды В ТЕМЕ письма
            subject = email_data['subject']

            print(f"🔍 Проверяю тему: {subject}")

            codes = self._extract_codes_from_subject(subject)

            if codes:
                print(f"✅ Найдены коды в теме: {codes}")
                results.append({
                    'email': email_data,
                    'codes': codes
                })
            else:
                print(f"❌ Коды не найдены в теме")

        return results

    def _is_email_recent(self, email_date: Optional[datetime]) -> bool:
        """
        Проверить, что письмо не старше MAX_CODE_AGE_MINUTES.

        Args:
            email_date: Дата письма

        Returns:
            bool: True если письмо свежее
        """
        if not email_date:
            print("⚠️ Дата письма отсутствует")
            return False

        # Если у даты письма есть timezone - приводим к UTC
        if email_date.tzinfo:
            # Конвертируем в UTC
            email_date_utc = email_date.astimezone(timezone.utc)
            # Убираем timezone для сравнения
            email_date_naive = email_date_utc.replace(tzinfo=None)
        else:
            # Если timezone нет - считаем что это UTC
            email_date_naive = email_date

        # Текущее время в UTC
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

        # Вычисляем возраст
        age = now_utc - email_date_naive

        max_age = timedelta(minutes=MAX_CODE_AGE_MINUTES)

        # DEBUG
        print(f"🕐 Дата письма (UTC): {email_date_naive}")
        print(f"🕐 Сейчас (UTC): {now_utc}")
        print(f"⏱️ Возраст письма: {age}")
        print(f"⏱️ Максимальный возраст: {max_age}")
        print(f"✅ Свежее? {age <= max_age}")

        return age <= max_age

    def _extract_codes(self, text: str) -> List[str]:
        """
        Извлечь коды из текста с помощью регулярных выражений.

        Args:
            text: Текст письма

        Returns:
            List[str]: Найденные коды
        """
        # Ищем все совпадения с паттерном
        matches = re.findall(CODE_REGEX, text)

        # Убираем дубликаты, сохраняя порядок
        seen = set()
        unique_codes = []

        for code in matches:
            if code not in seen:
                seen.add(code)
                unique_codes.append(code)

        return unique_codes

    def _extract_codes_from_subject(self, subject: str) -> List[str]:
        """
        Извлечь 2FA коды из ТЕМЫ письма.
        Простой и надёжный метод.

        Args:
            subject: Тема письма

        Returns:
            List[str]: Найденные коды
        """
        import re

        codes = []

        # Паттерн 1: Ищем все 6-значные числа
        pattern_6 = r'\b(\d{6})\b'
        matches_6 = re.findall(pattern_6, subject)
        codes.extend(matches_6)

        # Паттерн 2: Ищем 7-значные числа (если нужно)
        pattern_7 = r'\b(\d{7})\b'
        matches_7 = re.findall(pattern_7, subject)
        codes.extend(matches_7)

        # Паттерн 3: Ищем 8-значные числа (если нужно)
        pattern_8 = r'\b(\d{8})\b'
        matches_8 = re.findall(pattern_8, subject)
        codes.extend(matches_8)

        # Убираем дубликаты
        unique_codes = []
        seen = set()

        for code in codes:
            if code not in seen:
                seen.add(code)
                unique_codes.append(code)

        print(f"🔍 DEBUG: Найдено в теме '{subject}': {unique_codes}")

        return unique_codes

    def get_latest_code(self) -> Optional[str]:
        """
        Главная функция: получить самый свежий 2FA код.

        Returns:
            str: Найденный код или None
        """
        try:
            # Подключаемся
            if not self.connect():
                return None

            # Получаем последние письма
            emails = self.get_latest_emails()

            if not emails:
                print("📭 Писем не найдено")
                return None

            print(f"\n📬 Найдено писем: {len(emails)}")

            # Ищем коды
            emails_with_codes = self.find_codes_in_emails(emails)

            if not emails_with_codes:
                print("🔍 Коды не найдены в письмах")

                # ОТЛАДКА: Покажем что нашли в письмах
                print("\n🔍 Содержимое писем для отладки:")
                for i, email_data in enumerate(emails[:3], 1):
                    print(f"\n--- Письмо {i} ---")
                    print(f"От: {email_data['from']}")
                    print(f"Тема: {email_data['subject']}")
                    print(f"Дата: {email_data['date']}")
                    print(f"Первые 500 символов тела:\n{email_data['body'][:500]}")
                    print("---\n")

                return None

            # Берём первое письмо (самое свежее) с кодами
            latest = emails_with_codes[0]
            codes = latest['codes']

            # ОТЛАДКА: Покажем все найденные коды
            print(f"\n✅ Найдено кодов: {codes}")
            print(f"📧 Письмо от: {latest['email']['from']}")
            print(f"📧 Тема: {latest['email']['subject']}")

            if codes:
                code = codes[0]  # Первый код в письме
                print(f"✅ Выбран код: {code}")
                return code

            return None

        except Exception as e:
            print(f"❌ Ошибка получения кода: {e}")
            import traceback
            traceback.print_exc()
            return None

        finally:
            # Всегда отключаемся
            self.disconnect()


# Тестирование
if __name__ == '__main__':
    print("📧 Тестирование парсера почты\n")

    # Для теста нужны реальные данные
    print("⚠️  Для тестирования нужны реальные данные почты:")
    print("1. Email адрес")
    print("2. Пароль приложения")
    print("3. Провайдер (gmail/yandex/mail.ru/outlook)")
    print("\nЗапусти этот файл и введи данные для теста")

    # Раскомментируй для реального теста:
    email_address = input("Email: ")
    password = input("Пароль приложения: ")
    provider = input("Провайдер: ")

    parser = EmailParser(email_address, password, provider)
    code = parser.get_latest_code()

    if code:
        print(f"\n🎉 Успешно! Найден код: {code}")
    else:
        print("\n😞 Код не найден")