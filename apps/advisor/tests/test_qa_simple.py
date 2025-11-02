import pytest
from django.utils import timezone
from datetime import timedelta
from apps.advisor.qa_simple import try_simple_qa
from apps.customers.models import Customer
from apps.campaigns.models import Campaign
from apps.coupons.models import Coupon
from apps.redemptions.models import Redemption

@pytest.mark.django_db
def test_new_customers_today():
    """Тест подсчета новых клиентов за сегодня"""
    from apps.businesses.models import Business
    from django.contrib.auth import get_user_model
    
    User = get_user_model()
    user = User.objects.create_user(username='testuser', email='test@example.com')
    business = Business.objects.create(name='Test Business', owner=user)
    
    # Создаем клиента с first_seen сегодня
    Customer.objects.create(
        business=business, 
        phone_e164='+77001112233', 
        first_seen=timezone.now()
    )
    
    res = try_simple_qa(business, "Сколько сегодня новых клиентов?")
    assert res is not None
    assert "Новых клиентов" in res.text
    assert "1" in res.text

@pytest.mark.django_db
def test_issues_today():
    """Тест подсчета выдач купонов за сегодня"""
    from apps.businesses.models import Business
    from django.contrib.auth import get_user_model
    
    User = get_user_model()
    user = User.objects.create_user(username='testuser', email='test@example.com')
    business = Business.objects.create(name='Test Business', owner=user)
    campaign = Campaign.objects.create(
        business=business,
        name='Test Campaign',
        is_active=True
    )
    
    Coupon.objects.create(
        campaign=campaign, 
        phone='+7700', 
        issued_at=timezone.now()
    )
    
    res = try_simple_qa(business, "Сколько сегодня выдано купонов?")
    assert res is not None
    assert "Выдач купонов" in res.text
    assert "1" in res.text

@pytest.mark.django_db
def test_redeems_today():
    """Тест подсчета погашений за сегодня"""
    from apps.businesses.models import Business
    from django.contrib.auth import get_user_model
    
    User = get_user_model()
    user = User.objects.create_user(username='testuser', email='test@example.com')
    business = Business.objects.create(name='Test Business', owner=user)
    campaign = Campaign.objects.create(
        business=business,
        name='Test Campaign',
        is_active=True
    )
    coupon = Coupon.objects.create(
        campaign=campaign, 
        phone='+7700', 
        issued_at=timezone.now()
    )
    
    Redemption.objects.create(
        coupon=coupon, 
        created_at=timezone.now()
    )
    
    res = try_simple_qa(business, "Сколько сегодня погашений?")
    assert res is not None
    assert "Погашений" in res.text
    assert "1" in res.text

@pytest.mark.django_db
def test_active_campaigns():
    """Тест подсчета активных кампаний"""
    from apps.businesses.models import Business
    from django.contrib.auth import get_user_model
    
    User = get_user_model()
    user = User.objects.create_user(username='testuser', email='test@example.com')
    business = Business.objects.create(name='Test Business', owner=user)
    
    Campaign.objects.create(
        business=business,
        name='Active Campaign',
        is_active=True
    )
    Campaign.objects.create(
        business=business,
        name='Inactive Campaign',
        is_active=False
    )
    
    res = try_simple_qa(business, "Сколько активных кампаний?")
    assert res is not None
    assert "Активных кампаний" in res.text
    assert "1" in res.text

@pytest.mark.django_db
def test_total_customers():
    """Тест подсчета всего клиентов"""
    from apps.businesses.models import Business
    from django.contrib.auth import get_user_model
    
    User = get_user_model()
    user = User.objects.create_user(username='testuser', email='test@example.com')
    business = Business.objects.create(name='Test Business', owner=user)
    
    Customer.objects.create(business=business, phone_e164='+77001112233')
    Customer.objects.create(business=business, phone_e164='+77001112234')
    
    res = try_simple_qa(business, "Сколько всего клиентов?")
    assert res is not None
    assert "Всего клиентов" in res.text
    assert "2" in res.text

@pytest.mark.django_db
def test_conversion_rate():
    """Тест расчета конверсии"""
    from apps.businesses.models import Business
    from django.contrib.auth import get_user_model
    
    User = get_user_model()
    user = User.objects.create_user(username='testuser', email='test@example.com')
    business = Business.objects.create(name='Test Business', owner=user)
    campaign = Campaign.objects.create(
        business=business,
        name='Test Campaign',
        is_active=True
    )
    
    # Создаем 4 купона
    coupons = []
    for i in range(4):
        coupon = Coupon.objects.create(
            campaign=campaign, 
            phone=f'+770000000{i}', 
            issued_at=timezone.now()
        )
        coupons.append(coupon)
    
    # Погашаем 2 купона (50% CR)
    for coupon in coupons[:2]:
        Redemption.objects.create(
            coupon=coupon, 
            created_at=timezone.now()
        )
    
    res = try_simple_qa(business, "CR сегодня?")
    assert res is not None
    assert "CR" in res.text
    assert "50" in res.text

@pytest.mark.django_db
def test_no_match():
    """Тест что функция возвращает None для неподдерживаемых вопросов"""
    from apps.businesses.models import Business
    from django.contrib.auth import get_user_model
    
    User = get_user_model()
    user = User.objects.create_user(username='testuser', email='test@example.com')
    business = Business.objects.create(name='Test Business', owner=user)
    
    res = try_simple_qa(business, "Какая погода завтра?")
    assert res is None
