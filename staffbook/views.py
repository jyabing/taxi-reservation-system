from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .forms import DailySalesForm
from .models import DailySales

@login_required
def submit_sales(request):
    if request.method == 'POST':
        form = DailySalesForm(request.POST)
        if form.is_valid():
            sales = form.save(commit=False)
            sales.driver = request.user
            sales.save()
            return redirect('staffbook:sales_thanks')  # 录入成功页面
    else:
        form = DailySalesForm()
    
    return render(request, 'staffbook/submit_sales.html', {'form': form})

@login_required
def sales_thanks(request):
    return render(request, 'staffbook/sales_thanks.html')
