from django.shortcuts import render
from django.http import HttpResponse
from django.views.generic import View

def mainpage(request):
   return render(request, "mainpage.html")