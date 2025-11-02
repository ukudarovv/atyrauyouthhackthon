from django import forms

class ClaimForm(forms.Form):
    phone = forms.CharField(
        label='Номер телефона', 
        max_length=32,
        widget=forms.TextInput(attrs={
            'placeholder': '+7 (XXX) XXX-XX-XX',
            'class': 'w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500'
        })
    )
    agree = forms.BooleanField(
        label='Согласен(а) с условиями и обработкой персональных данных',
        widget=forms.CheckboxInput(attrs={
            'class': 'mr-2'
        })
    )
