import secrets
from django.utils import timezone
from .models import ReviewInvite, ReviewInviteSource

def gen_token() -> str:
    return secrets.token_urlsafe(9)

def create_invite(*, business, campaign=None, phone='', email='', source=ReviewInviteSource.MANUAL, ttl_hours: int|None=72):
    token = gen_token()
    while ReviewInvite.objects.filter(token=token).exists():
        token = gen_token()
    expires_at = timezone.now() + timezone.timedelta(hours=ttl_hours) if ttl_hours else None
    return ReviewInvite.objects.create(
        business=business, campaign=campaign, token=token,
        phone=phone or '', email=email or '', source=source, expires_at=expires_at
    )

def external_links_from_business(business) -> dict:
    """
    Ожидаем в Business.contacts:
    {
      "google_url": "https://g.page/..",
      "2gis_url": "https://2gis.kz/..",
      "yandex_url": "https://yandex.kz/profile/.."
    }
    """
    contacts = business.contacts or {}
    return {
        'google_url': contacts.get('google_url', ''),
        'gis2_url': contacts.get('2gis_url', ''),
        'yandex_url': contacts.get('yandex_url', ''),
    }
