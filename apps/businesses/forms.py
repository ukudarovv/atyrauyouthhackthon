from django import forms
from .models import Business, Location

class BusinessForm(forms.ModelForm):
    class Meta:
        model = Business
        fields = ('name', 'phone', 'address', 'timezone', 'brand_color', 'contacts')
        widgets = {
            'brand_color': forms.TextInput(attrs={'type': 'color'}),
            'contacts': forms.Textarea(attrs={'rows': 3, 'placeholder': 'JSON формат: {"email": "test@test.com", "website": "https://example.com"}'}),
        }

class LocationForm(forms.ModelForm):
    class Meta:
        model = Location
        fields = ('name', 'address', 'geo_lat', 'geo_lng', 'opening_hours', 'is_active')
        widgets = {
            'opening_hours': forms.Textarea(attrs={'rows': 3, 'placeholder': 'JSON формат: {"mon": "09:00-18:00", "tue": "09:00-18:00"}'}),
        }
