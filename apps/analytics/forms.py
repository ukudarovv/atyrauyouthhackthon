from django import forms
from django.utils import timezone

def default_range():
    end = timezone.localdate()
    start = end - timezone.timedelta(days=13)  # всего 14 дней
    return start, end

class DateRangeForm(forms.Form):
    start = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'border border-gray-300 rounded p-2 focus:outline-none focus:ring-2 focus:ring-blue-500'
        }),
        label='Начало'
    )
    end = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'border border-gray-300 rounded p-2 focus:outline-none focus:ring-2 focus:ring-blue-500'
        }),
        label='Конец'
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            s, e = default_range()
            self.initial['start'] = s
            self.initial['end'] = e

class CampaignFilterForm(forms.Form):
    campaign = forms.IntegerField(
        required=False, 
        widget=forms.Select(attrs={
            'class': 'border border-gray-300 rounded p-2 focus:outline-none focus:ring-2 focus:ring-blue-500'
        }),
        label='Кампания'
    )

    def __init__(self, business, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.campaigns.models import Campaign
        choices = [('', 'Все кампании')]
        choices += [(c.id, c.name) for c in Campaign.objects.filter(business=business).order_by('-id')]
        self.fields['campaign'].widget.choices = choices
