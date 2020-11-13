from decimal import Context
from email_validator import validate_email, EmailNotValidError
from validate_email import validate_email
from django.http import request
from django.shortcuts import redirect, render
from django.views import View
import json
from django.http import JsonResponse
from django.contrib.auth.models import User
from django.contrib import messages
from django.core.mail import EmailMessage
from django.utils.encoding import force_bytes, force_text, DjangoUnicodeDecodeError
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.contrib.sites.shortcuts import get_current_site
from django.urls import reverse
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.tokens import PasswordResetTokenGenerator
import threading

from .utils import account_activation_token
# Create your views here.


class UsernameValidationView(View):
    def post(self, request):
        data = json.loads(request.body)
        username = data['username']

        if not str(username).isalnum():
            return JsonResponse({'username_error': 'username should only contain alphanumeric characters'}, status=400)
        if User.objects.filter(username=username).exists():
            return JsonResponse({'username_error': 'sorry username in use, choose another one'}, status=409)

        return JsonResponse({'username_valid': True})


# this is for froguction: pip install email-validator #https://pypi.org/project/email-validator/
#from email_validator import validate_email, EmailNotValidError
# this is for api test: pip install validate_email #https://pypi.org/project/validate_email/#description

class EmailThread(threading.Thread):
    def __init__(self, email):
        self.email = email
        threading.Thread.__init__(self)

    def run(self):
        self.email.send(fail_silently=False)


class EmailValidationView(View):
    def post(self, request):
        data = json.loads(request.body)
        email = data['email']

        if not validate_email(email):
            return JsonResponse({'email_error': 'email is invalid'}, status=400)
        if User.objects.filter(email=email).exists():
            return JsonResponse({'email_error': 'sorry email in use, choose another one'}, status=409)

        return JsonResponse({'email_valid': True})


class RegistrationView(View):
    def get(self, request):
        return render(request, 'authentication/register.html')

    def post(self, request):

        username = request.POST['username']
        email = request.POST['email']
        password = request.POST['password']

        context = {
            'fieldValues': request.POST
        }

        if not User.objects.filter(username=username).exists():
            if not User.objects.filter(email=email).exists():

                if len(password) < 3:
                    messages.error(
                        request, 'Password too short. It should be at least 6.')
                    return render(request, 'authentication/register.html', context)

                user = User.objects.create_user(username=username, email=email)
                #user = User.objects.create(username=username, email=email)
                user.set_password(password)
                user.is_active = False
                user.save()

                # email_body = {
                #     'user': user,
                #     'domain': get_current_site(request).domain,
                #     'uid': urlsafe_base64_encode(force_bytes(user.pk)),
                #     'token': account_activation_token.make_token(user),
                # }
                uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
                domain = get_current_site(request).domain
                link = reverse('activate', kwargs={
                               'uidb64': uidb64, 'token': account_activation_token.make_token(user)})
                activate_url = 'http://'+domain+link

                email_subject = "Activate your account"
                email_body = 'Hi '+user.username + \
                    '! Please use this link to verify your account\n' + activate_url

                # https://docs.djangoproject.com/en/3.1/topics/email/#emailmessage-objects
                email = EmailMessage(
                    email_subject,
                    email_body,
                    'alim.abdul.5915@gmail.com',
                    [email],
                )
                # email.send(fail_silently=False) #or
                EmailThread(email).start()
                messages.success(
                    request, 'Account created successfully.Please check email for verification.')
                return render(request, 'authentication/register.html')

        return render(request, 'authentication/register.html')


class VerificationView(View):
    def get(self, request, uidb64, token):
        try:
            id = force_text(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk=id)

            if not account_activation_token.check_token(user, token):
                return redirect('login'+'?message='+'User already activated')
            if user.is_active:
                return redirect('login')

            user.is_active = True
            user.save()

            messages.success(request, 'Account activated successfully')
            return redirect('login')

        except Exception as ex:
            pass
        return redirect('login')


class LoginView(View):
    def get(self, request):
        return render(request, 'authentication/login.html')

    def post(self, request):
        username = request.POST['username']
        password = request.POST['password']

        if username and password:
            user = authenticate(username=username, password=password)

            if user:
                if user.is_active:
                    login(request, user)
                    messages.success(request, 'Welcome, ' +
                                     user.username + ' your are now logged in')
                    return redirect('expenses')
                else:
                    # if user is not active
                    messages.error(
                        request, 'Account is not activate, please check your email')
                    return render(request, 'authentication/login.html')
            else:
                # if user is not registered
                messages.error(
                    request, 'Username or Password does not match.')
                return render(request, 'authentication/login.html')

        # if user is not registered
        messages.error(request, 'Please fill all fields')
        return render(request, 'authentication/login.html')


def logoutView(request):
    logout(request)
    messages.success(request, 'You have been logged out')
    return redirect('login')


class PasswordReset(View):
    def get(self, request):

        return render(request, 'authentication/reset-password.html')

    def post(self, request):
        email = request.POST['email']
        user = User.objects.filter(email=email)
        Context = {
            'values': request.POST
        }
        if not validate_email(email):
            messages.error(request, 'Please insert a valid email')
            return render(request, 'authentication/reset-password.html', Context)
        else:

            if user.exists():
                email_contents = {
                    'user': user[0],
                    'domain': get_current_site(request).domain,
                    'uid': urlsafe_base64_encode(force_bytes(user[0].pk)),
                    'token': PasswordResetTokenGenerator().make_token(user[0]),
                }

                link = reverse('set-new-password', kwargs={
                    'uidb64': email_contents['uid'], 'token': email_contents['token']})
                reset_url = 'http://'+email_contents['domain']+link

                email_subject = "Password reset instructions"
                email_body = 'Hi there, Please click to this link below to reset your password\n' + reset_url

                # https://docs.djangoproject.com/en/3.1/topics/email/#emailmessage-objects
                email = EmailMessage(
                    email_subject,
                    email_body,
                    'alim.abdul.5915@gmail.com',
                    [email],
                )
                # email.send(fail_silently=False) #or
                EmailThread(email).start()
                messages.success(
                    request, 'We have sent you an email to reset your password.')
                return redirect('login')
            else:
                messages.success(
                    request, 'This email is not registered')
                return render(request, 'authentication/reset-password.html')


class CompletePasswordReset(View):
    def get(self, request, uidb64, token):
        context = {
            'uidb64': uidb64,
            'token': token
        }
        return render(request, 'authentication/set-new-password.html', context)

    def post(self, request, uidb64, token):
        context = {
            'uidb64': uidb64,
            'token': token
        }
        password = request.POST['password']
        password2 = request.POST['password2']

        if password != password2:
            messages.error(request, 'Passwords do not match.')
            return render(request, 'authentication/set-new-password.html', context)

        if len(password) < 3:
            messages.error(
                request, 'Password too short. It should be at least 3.')
            return render(request, 'authentication/set-new-password.html', context)

        try:
            user_id = force_text(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk=user_id)
            if not PasswordResetTokenGenerator().check_token(user, token):
                messages.info(
                    request, 'Password link is invalid, please request a new one')
                return render(request, 'authentication/reset-password.html')
            else:
                user.set_password(password)
                user.save()
                messages.success(request, 'Password reset successfull')
                return redirect('login')
        except Exception as identifier:
            messages.info(request, 'Something went wrong,try again')
            return render(request, 'authentication/set-new-password.html', context)
