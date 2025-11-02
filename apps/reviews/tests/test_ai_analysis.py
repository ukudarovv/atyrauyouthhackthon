import pytest
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from apps.businesses.models import Business
from apps.reviews.models import Review
from apps.reviews.tasks import analyze_review_task

User = get_user_model()

class ReviewAIAnalysisTestCase(TestCase):
    
    def setUp(self):
        """Настройка тестовых данных"""
        self.user = User.objects.create_user(
            username='testowner', 
            password='testpass123',
            role='owner'
        )
        
        self.business = Business.objects.create(
            owner=self.user,
            name='Test Cafe'
        )
    
    @override_settings(AI_PROVIDER='dummy')
    def test_positive_review_analysis(self):
        """Тест анализа позитивного отзыва"""
        review = Review.objects.create(
            business=self.business,
            rating=5,
            text='Очень вкусно и быстро! Отличный сервис!'
        )
        
        # Запускаем анализ
        result = analyze_review_task(review.id)
        
        # Проверяем результат
        self.assertTrue(result['success'])
        
        # Обновляем объект из базы
        review.refresh_from_db()
        
        # Проверяем, что анализ выполнен
        self.assertIsNotNone(review.ai_sentiment)
        self.assertIsInstance(review.ai_labels, list)
        self.assertIsInstance(review.ai_toxic, bool)
        self.assertIsInstance(review.ai_summary, str)
        
        # Проверяем, что тональность положительная
        self.assertGreater(review.ai_sentiment, 0)
        
        # Проверяем, что отзыв не токсичный
        self.assertFalse(review.ai_toxic)
        
        # Проверяем, что есть темы
        self.assertTrue(len(review.ai_labels) > 0)
        
        # Проверяем, что есть резюме
        self.assertTrue(len(review.ai_summary) > 0)
    
    @override_settings(AI_PROVIDER='dummy')
    def test_negative_review_analysis(self):
        """Тест анализа негативного отзыва"""
        review = Review.objects.create(
            business=self.business,
            rating=1,
            text='Ужасно медленно и невкусно! Плохое обслуживание!'
        )
        
        # Запускаем анализ
        result = analyze_review_task(review.id)
        
        # Проверяем результат
        self.assertTrue(result['success'])
        
        # Обновляем объект из базы
        review.refresh_from_db()
        
        # Проверяем, что тональность отрицательная
        self.assertLess(review.ai_sentiment, 0)
        
        # Проверяем, что отзыв не токсичный (слова в тесте не токсичные)
        self.assertFalse(review.ai_toxic)
    
    @override_settings(AI_PROVIDER='dummy')
    def test_toxic_review_analysis(self):
        """Тест анализа токсичного отзыва"""
        review = Review.objects.create(
            business=self.business,
            rating=1,
            text='Это полный отстой! Идиоты работают!',
            is_published=True  # Изначально опубликован
        )
        
        # Запускаем анализ
        result = analyze_review_task(review.id)
        
        # Проверяем результат
        self.assertTrue(result['success'])
        
        # Обновляем объект из базы
        review.refresh_from_db()
        
        # Проверяем, что отзыв помечен как токсичный
        self.assertTrue(review.ai_toxic)
        
        # Проверяем, что токсичный отзыв был скрыт
        self.assertFalse(review.is_published)
    
    @override_settings(AI_PROVIDER='dummy')
    def test_sentiment_ranges(self):
        """Тест диапазонов тональности"""
        # Позитивный отзыв
        positive_review = Review.objects.create(
            business=self.business,
            rating=5,
            text='Супер вкусно и отлично!'
        )
        
        analyze_review_task(positive_review.id)
        positive_review.refresh_from_db()
        
        self.assertGreaterEqual(positive_review.ai_sentiment, -100)
        self.assertLessEqual(positive_review.ai_sentiment, 100)
        
        # Негативный отзыв
        negative_review = Review.objects.create(
            business=self.business,
            rating=1,
            text='Ужасно плохо!'
        )
        
        analyze_review_task(negative_review.id)
        negative_review.refresh_from_db()
        
        self.assertGreaterEqual(negative_review.ai_sentiment, -100)
        self.assertLessEqual(negative_review.ai_sentiment, 100)
    
    @override_settings(AI_PROVIDER='dummy')
    def test_label_detection(self):
        """Тест определения тем"""
        review = Review.objects.create(
            business=self.business,
            rating=4,
            text='Официант был быстрым, еда вкусная, но цена дорогая'
        )
        
        analyze_review_task(review.id)
        review.refresh_from_db()
        
        # Проверяем, что определились темы
        self.assertIsInstance(review.ai_labels, list)
        
        # Проверяем, что есть ожидаемые темы
        expected_labels = ['сервис', 'вкус', 'цена']
        for label in expected_labels:
            self.assertIn(label, review.ai_labels)
    
    def test_review_not_found(self):
        """Тест обработки несуществующего отзыва"""
        result = analyze_review_task(99999)
        
        self.assertFalse(result['success'])
        self.assertIn('not found', result['error'].lower())
    
    @override_settings(AI_PROVIDER='dummy')
    def test_empty_review_analysis(self):
        """Тест анализа пустого отзыва"""
        review = Review.objects.create(
            business=self.business,
            rating=3,
            text=''  # Пустой текст
        )
        
        result = analyze_review_task(review.id)
        
        # Даже пустой отзыв должен анализироваться
        self.assertTrue(result['success'])
        
        review.refresh_from_db()
        self.assertIsNotNone(review.ai_sentiment)
        self.assertIsInstance(review.ai_labels, list)
    
    @override_settings(AI_PROVIDER='dummy')
    def test_summary_length_limit(self):
        """Тест ограничения длины резюме"""
        # Создаем отзыв с длинным текстом
        long_text = 'Отлично! ' * 100  # Длинный текст
        
        review = Review.objects.create(
            business=self.business,
            rating=5,
            text=long_text
        )
        
        analyze_review_task(review.id)
        review.refresh_from_db()
        
        # Проверяем, что резюме не превышает лимит
        self.assertLessEqual(len(review.ai_summary), 280)
    
    @override_settings(AI_PROVIDER='dummy')
    def test_labels_limit(self):
        """Тест ограничения количества тем"""
        # Создаем отзыв, который может породить много тем
        review = Review.objects.create(
            business=self.business,
            rating=4,
            text='Официант был быстрый, еда вкусная, цена дорогая, '
                 'чисто, атмосфера хорошая, персонал вежливый, '
                 'порции большие, меню разнообразное, доставка быстрая'
        )
        
        analyze_review_task(review.id)
        review.refresh_from_db()
        
        # Проверяем, что количество тем не превышает лимит
        self.assertLessEqual(len(review.ai_labels), 8)
