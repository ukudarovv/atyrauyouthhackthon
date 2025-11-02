from django import forms
from .models import Campaign, Landing

class CampaignForm(forms.ModelForm):
    class Meta:
        model = Campaign
        fields = ('business', 'location', 'type', 'name', 'starts_at', 'ends_at', 'is_active', 'issue_limit', 'per_phone_limit', 'description', 'terms', 'landing_theme')
        widgets = {
            'starts_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'ends_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'description': forms.Textarea(attrs={'rows': 3}),
            'terms': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Фильтруем бизнесы и локации по владельцу
        if user:
            self.fields['business'].queryset = user.owned_businesses.all()
            if 'business' in self.data or self.instance.pk:
                try:
                    business_id = int(self.data.get('business', self.instance.business_id))
                    self.fields['location'].queryset = user.owned_businesses.get(pk=business_id).locations.all()
                except (ValueError, TypeError):
                    self.fields['location'].queryset = self.fields['location'].queryset.none()
            else:
                self.fields['location'].queryset = self.fields['location'].queryset.none()

class LandingForm(forms.ModelForm):
    class Meta:
        model = Landing
        fields = ('headline', 'body_md', 'cta_text', 'hero_image', 'seo_title', 'seo_desc', 'og_image', 'primary_color')
        widgets = {
            'primary_color': forms.TextInput(attrs={'type': 'color'}),
            'body_md': forms.Textarea(attrs={'rows': 5, 'placeholder': 'Описание акции, условия участия...'}),
            'seo_title': forms.TextInput(attrs={'placeholder': 'SEO заголовок для поисковиков'}),
            'seo_desc': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Краткое описание для поисковиков (до 160 символов)'}),
        }
