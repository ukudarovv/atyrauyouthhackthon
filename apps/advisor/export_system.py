import io
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List
import pandas as pd
from django.http import HttpResponse
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.lib.colors import HexColor

class ExportSystem:
    """Система экспорта данных в различные форматы"""
    
    def __init__(self, business):
        self.business = business
        self.styles = getSampleStyleSheet()
        
    def export_analytics_excel(self, data: Dict[str, Any], format_type: str = 'excel') -> HttpResponse:
        """Экспорт аналитики в Excel с красивым форматированием"""
        
        # Собираем данные
        analytics_data = self._prepare_analytics_data(data)
        
        if format_type == 'excel':
            return self._create_excel_report(analytics_data)
        elif format_type == 'pdf':
            return self._create_pdf_report(analytics_data)
        else:
            return self._create_csv_report(analytics_data)
    
    def _prepare_analytics_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Подготавливает данные для экспорта"""
        from apps.coupons.models import Coupon
        from apps.redemptions.models import Redemption
        from apps.campaigns.models import Campaign
        from apps.customers.models import Customer
        from django.db.models import Count, Sum, Avg
        from django.db.models.functions import TruncDate
        
        end_date = timezone.now()
        start_date = end_date - timedelta(days=30)
        
        # Основные метрики
        total_customers = Customer.objects.filter(business=self.business).count()
        new_customers_30d = Customer.objects.filter(
            business=self.business, 
            first_seen__gte=start_date
        ).count()
        
        total_coupons = Coupon.objects.filter(campaign__business=self.business).count()
        total_redemptions = Redemption.objects.filter(coupon__campaign__business=self.business).count()
        
        cr_rate = (total_redemptions / total_coupons * 100) if total_coupons > 0 else 0
        
        # Топ кампаний
        top_campaigns = Campaign.objects.filter(
            business=self.business, 
            is_active=True
        ).annotate(
            redemption_count=Count('coupons__redemption')
        ).order_by('-redemption_count')[:10]
        
        # Дневная статистика
        daily_stats = Redemption.objects.filter(
            coupon__campaign__business=self.business,
            redeemed_at__gte=start_date
        ).annotate(
            date=TruncDate('redeemed_at')
        ).values('date').annotate(
            count=Count('id')
        ).order_by('date')
        
        return {
            'business_name': self.business.name,
            'report_date': timezone.now(),
            'period': f"{start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}",
            'summary': {
                'total_customers': total_customers,
                'new_customers_30d': new_customers_30d,
                'total_coupons': total_coupons,
                'total_redemptions': total_redemptions,
                'conversion_rate': round(cr_rate, 2)
            },
            'top_campaigns': [
                {
                    'name': camp.name,
                    'redemptions': camp.redemption_count,
                    'status': 'Активна' if camp.is_active else 'Неактивна'
                }
                for camp in top_campaigns
            ],
            'daily_stats': [
                {
                    'date': stat['date'].strftime('%d.%m.%Y'),
                    'redemptions': stat['count']
                }
                for stat in daily_stats
            ]
        }
    
    def _create_excel_report(self, data: Dict[str, Any]) -> HttpResponse:
        """Создает Excel отчет с форматированием"""
        output = io.BytesIO()
        
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Лист 1: Сводка
            summary_df = pd.DataFrame([data['summary']]).T
            summary_df.columns = ['Значение']
            summary_df.index = [
                'Всего клиентов',
                'Новые клиенты (30 дней)',
                'Всего купонов',
                'Всего погашений',
                'Конверсия (%)'
            ]
            summary_df.to_excel(writer, sheet_name='Сводка')
            
            # Лист 2: Топ кампаний
            if data['top_campaigns']:
                campaigns_df = pd.DataFrame(data['top_campaigns'])
                campaigns_df.columns = ['Название кампании', 'Погашения', 'Статус']
                campaigns_df.to_excel(writer, sheet_name='Топ кампаний', index=False)
            
            # Лист 3: Дневная статистика
            if data['daily_stats']:
                daily_df = pd.DataFrame(data['daily_stats'])
                daily_df.columns = ['Дата', 'Погашения']
                daily_df.to_excel(writer, sheet_name='По дням', index=False)
            
            # Форматирование
            workbook = writer.book
            for sheet_name in workbook.sheetnames:
                worksheet = workbook[sheet_name]
                
                # Автоширина столбцов
                for column in worksheet.columns:
                    max_length = 0
                    column_letter = column[0].column_letter
                    for cell in column:
                        try:
                            if len(str(cell.value)) > max_length:
                                max_length = len(str(cell.value))
                        except:
                            pass
                    adjusted_width = min(max_length + 2, 50)
                    worksheet.column_dimensions[column_letter].width = adjusted_width
        
        output.seek(0)
        
        response = HttpResponse(
            output.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        filename = f"analytics_{data['business_name']}_{timezone.now().strftime('%Y%m%d_%H%M')}.xlsx"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response
    
    def _create_pdf_report(self, data: Dict[str, Any]) -> HttpResponse:
        """Создает PDF отчет с графиками"""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        story = []
        
        # Заголовок
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=24,
            textColor=HexColor('#2563EB'),
            alignment=1,  # CENTER
            spaceAfter=30
        )
        
        story.append(Paragraph(f"📊 Аналитический отчет", title_style))
        story.append(Paragraph(f"<b>{data['business_name']}</b>", self.styles['Heading2']))
        story.append(Paragraph(f"Период: {data['period']}", self.styles['Normal']))
        story.append(Paragraph(f"Дата создания: {data['report_date'].strftime('%d.%m.%Y %H:%M')}", self.styles['Normal']))
        story.append(Spacer(1, 20))
        
        # Сводная таблица
        story.append(Paragraph("🎯 Ключевые метрики", self.styles['Heading2']))
        
        summary_data = [
            ['Метрика', 'Значение'],
            ['Всего клиентов', f"{data['summary']['total_customers']:,}"],
            ['Новые клиенты (30 дней)', f"{data['summary']['new_customers_30d']:,}"],
            ['Всего купонов', f"{data['summary']['total_coupons']:,}"],
            ['Всего погашений', f"{data['summary']['total_redemptions']:,}"],
            ['Конверсия', f"{data['summary']['conversion_rate']:.2f}%"]
        ]
        
        summary_table = Table(summary_data, colWidths=[3*inch, 2*inch])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), HexColor('#3B82F6')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), HexColor('#F8FAFC')),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        story.append(summary_table)
        story.append(Spacer(1, 20))
        
        # Топ кампаний
        if data['top_campaigns']:
            story.append(Paragraph("🏆 Топ кампаний", self.styles['Heading2']))
            
            campaigns_data = [['Название', 'Погашения', 'Статус']]
            for camp in data['top_campaigns'][:10]:
                campaigns_data.append([
                    camp['name'][:30] + ('...' if len(camp['name']) > 30 else ''),
                    str(camp['redemptions']),
                    camp['status']
                ])
            
            campaigns_table = Table(campaigns_data, colWidths=[3*inch, 1*inch, 1*inch])
            campaigns_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), HexColor('#10B981')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BACKGROUND', (0, 1), (-1, -1), HexColor('#F0FDF4')),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            
            story.append(campaigns_table)
        
        # Создаем PDF
        doc.build(story)
        buffer.seek(0)
        
        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        filename = f"report_{data['business_name']}_{timezone.now().strftime('%Y%m%d_%H%M')}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response
    
    def _create_csv_report(self, data: Dict[str, Any]) -> HttpResponse:
        """Создает CSV отчет"""
        output = io.StringIO()
        
        # Заголовок
        output.write(f"Аналитический отчет - {data['business_name']}\n")
        output.write(f"Период: {data['period']}\n")
        output.write(f"Дата создания: {data['report_date'].strftime('%d.%m.%Y %H:%M')}\n\n")
        
        # Сводка
        output.write("КЛЮЧЕВЫЕ МЕТРИКИ\n")
        output.write("Метрика,Значение\n")
        for key, value in data['summary'].items():
            output.write(f"{key},{value}\n")
        
        output.write("\nТОП КАМПАНИЙ\n")
        output.write("Название,Погашения,Статус\n")
        for camp in data['top_campaigns']:
            output.write(f"{camp['name']},{camp['redemptions']},{camp['status']}\n")
        
        response = HttpResponse(output.getvalue(), content_type='text/csv; charset=utf-8')
        filename = f"analytics_{data['business_name']}_{timezone.now().strftime('%Y%m%d_%H%M')}.csv"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response

def export_chat_history(session, format_type='pdf'):
    """Экспорт истории чата"""
    if format_type == 'pdf':
        return _export_chat_pdf(session)
    else:
        return _export_chat_txt(session)

def _export_chat_pdf(session):
    """Экспорт чата в PDF"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    story = []
    styles = getSampleStyleSheet()
    
    # Заголовок
    story.append(Paragraph(f"💬 История чата - {session.business.name}", styles['Title']))
    story.append(Paragraph(f"Пользователь: {session.user.username}", styles['Normal']))
    story.append(Paragraph(f"Дата: {session.created_at.strftime('%d.%m.%Y %H:%M')}", styles['Normal']))
    story.append(Spacer(1, 20))
    
    # Сообщения
    for msg in session.messages.order_by('created_at'):
        if msg.role == 'user':
            story.append(Paragraph(f"👤 <b>Вы:</b> {msg.content.get('text', '')}", styles['Normal']))
        else:
            mode = msg.content.get('mode', 'unknown')
            mode_emoji = {'quick': '⚡', 'rule_based': '🎯', 'analytics': '📊'}.get(mode, '🤖')
            story.append(Paragraph(f"{mode_emoji} <b>AI:</b> {msg.content.get('text', '')}", styles['Normal']))
        story.append(Spacer(1, 10))
    
    doc.build(story)
    buffer.seek(0)
    
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    filename = f"chat_history_{session.id}_{timezone.now().strftime('%Y%m%d_%H%M')}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    return response

def _export_chat_txt(session):
    """Экспорт чата в TXT"""
    output = io.StringIO()
    
    output.write(f"История чата - {session.business.name}\n")
    output.write(f"Пользователь: {session.user.username}\n")
    output.write(f"Дата: {session.created_at.strftime('%d.%m.%Y %H:%M')}\n")
    output.write("=" * 50 + "\n\n")
    
    for msg in session.messages.order_by('created_at'):
        timestamp = msg.created_at.strftime('%H:%M')
        if msg.role == 'user':
            output.write(f"[{timestamp}] ВЫ: {msg.content.get('text', '')}\n\n")
        else:
            mode = msg.content.get('mode', 'unknown')
            output.write(f"[{timestamp}] AI ({mode}): {msg.content.get('text', '')}\n\n")
    
    response = HttpResponse(output.getvalue(), content_type='text/plain; charset=utf-8')
    filename = f"chat_history_{session.id}_{timezone.now().strftime('%Y%m%d_%H%M')}.txt"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    return response
