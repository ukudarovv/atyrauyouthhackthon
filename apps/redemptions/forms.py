from django import forms

class RedeemForm(forms.Form):
    """Форма для погашения купона"""
    code = forms.CharField(
        label='Код купона',
        max_length=16,
        widget=forms.TextInput(attrs={
            'placeholder': 'Введите код купона',
            'class': 'w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono text-lg',
            'autocomplete': 'off',
            'autofocus': True
        })
    )
    
    amount = forms.DecimalField(
        label='Сумма чека, ₸',
        max_digits=10,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(attrs={
            'placeholder': '0.00',
            'class': 'w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500',
            'step': '0.01',
            'min': '0'
        })
    )
    
    pos_ref = forms.CharField(
        label='Номер чека',
        max_length=64,
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'Номер чека или операции',
            'class': 'w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500'
        })
    )
    
    note = forms.CharField(
        label='Комментарий',
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'Дополнительная информация',
            'class': 'w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500'
        })
    )

    def clean_code(self):
        """Очищаем и нормализуем код купона"""
        code = self.cleaned_data['code']
        return code.strip().upper()
