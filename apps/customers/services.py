"""
Сервисы для агрегации клиентов и RFM анализа
"""
import re
import logging
from django.utils import timezone
from decimal import Decimal
from apps.customers.models import Customer
from apps.coupons.models import Coupon

logger = logging.getLogger(__name__)


def normalize_phone(phone: str) -> str:
    """
    Нормализует номер телефона в формат E.164
    """
    if not phone:
        return ""
    
    # Убираем все нецифровые символы
    digits = re.sub(r'\D', '', phone)
    
    # Конвертируем 8 в 7 для российских номеров
    if digits.startswith('8') and len(digits) == 11:
        digits = '7' + digits[1:]
    
    # Добавляем + если его нет
    if not digits.startswith('+'):
        digits = '+' + digits
    
    return digits


def upsert_customer_from_issue(coupon: Coupon):
    """
    Обновляет или создает клиента при выдаче купона
    """
    phone = normalize_phone(coupon.phone)
    if not phone:
        logger.warning(f"Empty phone for coupon {coupon.id}")
        return None
    
    try:
        customer, created = Customer.objects.get_or_create(
            business=coupon.campaign.business,
            phone_e164=phone,
            defaults={
                'first_seen': coupon.issued_at or timezone.now(),
                'last_issue_at': coupon.issued_at or timezone.now(),
                'issues_count': 1
            }
        )
        
        if not created:
            # Обновляем существующего клиента
            customer.issues_count = (customer.issues_count or 0) + 1
            customer.first_seen = customer.first_seen or (coupon.issued_at or timezone.now())
            customer.last_issue_at = max(
                customer.last_issue_at or customer.first_seen, 
                coupon.issued_at or timezone.now()
            )
            customer.save(update_fields=['issues_count', 'first_seen', 'last_issue_at'])
        
        logger.info(f"Customer {customer.id} updated from issue (coupon {coupon.id})")
        return customer
        
    except Exception as e:
        logger.error(f"Error updating customer from issue {coupon.id}: {e}")
        return None


def upsert_customer_from_redeem(redemption):
    """
    Обновляет или создает клиента при погашении купона
    """
    coupon = redemption.coupon
    phone = normalize_phone(coupon.phone)
    if not phone:
        logger.warning(f"Empty phone for redemption {redemption.id}")
        return None
    
    try:
        customer, created = Customer.objects.get_or_create(
            business=coupon.campaign.business,
            phone_e164=phone,
            defaults={
                'first_seen': redemption.created_at,
                'last_redeem_at': redemption.created_at,
                'redeems_count': 1,
                'redeem_amount_total': getattr(redemption, 'amount', Decimal('0.00')) or Decimal('0.00')
            }
        )
        
        if not created:
            # Обновляем существующего клиента
            customer.redeems_count = (customer.redeems_count or 0) + 1
            customer.last_redeem_at = max(
                customer.last_redeem_at or redemption.created_at, 
                redemption.created_at
            )
            
            # Добавляем сумму погашения если есть
            if hasattr(redemption, 'amount') and redemption.amount:
                customer.redeem_amount_total += redemption.amount
            
            customer.save(update_fields=[
                'redeems_count', 'last_redeem_at', 'redeem_amount_total'
            ])
        
        logger.info(f"Customer {customer.id} updated from redeem (redemption {redemption.id})")
        return customer
        
    except Exception as e:
        logger.error(f"Error updating customer from redeem {redemption.id}: {e}")
        return None


def calculate_rfm_scores(business):
    """
    Пересчитывает RFM скоры для всех клиентов бизнеса
    """
    from datetime import timedelta
    
    today = timezone.localdate()
    customers = Customer.objects.filter(business=business)
    
    if not customers.exists():
        logger.info(f"No customers found for business {business.id}")
        return
    
    # 1. Обновляем recency_days
    for customer in customers.iterator():
        if customer.last_redeem_at:
            customer.recency_days = (today - customer.last_redeem_at.date()).days
        else:
            customer.recency_days = 9999
        customer.save(update_fields=['recency_days'])
    
    # 2. Получаем данные для квантилей
    customers_data = list(customers.values_list(
        'id', 'recency_days', 'redeems_count', 'redeem_amount_total'
    ))
    
    if not customers_data:
        return
    
    # 3. Вычисляем квантили
    def calculate_quantiles(values, k=5):
        """Вычисляет квантили для разделения на k групп"""
        if not values:
            return [0] * (k - 1)
        
        sorted_values = sorted(values)
        n = len(sorted_values)
        quantiles = []
        
        for i in range(1, k):
            index = int(n * i / k)
            if index < n:
                quantiles.append(sorted_values[index])
            else:
                quantiles.append(sorted_values[-1])
        
        return quantiles
    
    # Извлекаем значения
    recency_values = [row[1] for row in customers_data if row[1] < 9999]  # Исключаем 9999
    frequency_values = [row[2] for row in customers_data]
    monetary_values = [float(row[3]) for row in customers_data if row[3] > 0]
    
    r_quantiles = calculate_quantiles(recency_values)
    f_quantiles = calculate_quantiles(frequency_values)
    m_quantiles = calculate_quantiles(monetary_values)
    
    logger.info(f"RFM quantiles for business {business.id}:")
    logger.info(f"R: {r_quantiles}, F: {f_quantiles}, M: {m_quantiles}")
    
    # 4. Функция для определения скора
    def get_score(value, quantiles, reverse=False):
        """Определяет скор на основе квантилей"""
        if not quantiles:
            return 1
        
        score = 1
        for i, threshold in enumerate(quantiles, start=1):
            if (value <= threshold and not reverse) or (value >= threshold and reverse):
                score = i
                break
            score = i + 1
        
        return max(1, min(5, score))
    
    # 5. Обновляем скоры
    updated_count = 0
    for customer_id, recency, frequency, monetary in customers_data:
        try:
            customer = Customer.objects.get(id=customer_id)
            
            # Recency: меньше дней = лучше (reverse=True)
            customer.r_score = get_score(recency, r_quantiles, reverse=True)
            
            # Frequency: больше = лучше
            customer.f_score = get_score(frequency, f_quantiles, reverse=False)
            
            # Monetary: больше = лучше
            customer.m_score = get_score(float(monetary), m_quantiles, reverse=False)
            
            customer.save(update_fields=['r_score', 'f_score', 'm_score'])
            updated_count += 1
            
        except Customer.DoesNotExist:
            continue
        except Exception as e:
            logger.error(f"Error updating RFM for customer {customer_id}: {e}")
    
    logger.info(f"Updated RFM scores for {updated_count} customers in business {business.id}")


def get_customer_stats(business):
    """
    Возвращает статистику по клиентам бизнеса
    """
    customers = Customer.objects.filter(business=business)
    
    total = customers.count()
    if total == 0:
        return {
            'total': 0,
            'new': 0,
            'active': 0,
            'vip': 0,
            'churn_risk': 0,
            'dormant': 0
        }
    
    # Считаем сегменты
    new_count = sum(1 for c in customers.iterator() if c.is_new)
    vip_count = sum(1 for c in customers.iterator() if c.is_vip)
    churn_risk_count = sum(1 for c in customers.iterator() if c.is_churn_risk)
    
    active_count = customers.filter(recency_days__lte=14, redeems_count__gte=2).count()
    dormant_count = customers.filter(recency_days__gte=90).count()
    
    return {
        'total': total,
        'new': new_count,
        'active': active_count,
        'vip': vip_count,
        'churn_risk': churn_risk_count,
        'dormant': dormant_count
    }
