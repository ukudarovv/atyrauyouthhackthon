from django import forms
from .models import Review

class PublicReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ('rating','text','publish_consent')
        widgets = {
            'rating': forms.Select(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500'
            }),
            'text': forms.Textarea(attrs={
                'rows': 4,
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500',
                'placeholder': 'Поделитесь впечатлениями о визите (необязательно)'
            }),
            'publish_consent': forms.CheckboxInput(attrs={
                'class': 'h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded'
            })
        }
        labels = {
            'rating': 'Оценка',
            'text': 'Комментарий',
            'publish_consent': 'Согласен на публикацию отзыва'
        }
