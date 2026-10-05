from django.utils import timezone
from django.db import models
from django.contrib.auth.models import User

# Create your models here.
category_choices=[
        ("Salary","Salary"),
        ("Food","Food"),
        ("Groceries","Groceries"),
        ("Travel","Travel"),
        ("Shopping","Shopping"),
        ("Bills","Bills"),
        ("Entertainment","Entertainment"),
        ("Other","Other"),
    ]
class Transactions(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    type_choices=[
        ("Income","Income"),
        ("Expense","Expense"),
    ]
    types=models.CharField(
        max_length=10,choices=type_choices,default="Income")
    
    # Income transactions may use a user-defined "Other" category.
    # Choices remain useful for the standard expense categories, but are not a
    # database constraint, so custom income labels can be stored safely.
    category = models.CharField(
        max_length=100, choices=category_choices, default="Salary")
    date = models.DateField(default=timezone.now)
    created_at= models.DateTimeField(auto_now_add=True)

class Budget(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    category = models.CharField(
        max_length=20,choices=category_choices,default="Salary")
    limit  = models.DecimalField(max_digits=10, decimal_places=2)
    

