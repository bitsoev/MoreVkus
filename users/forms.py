from django import forms


class LoginUsersForm(forms.Form):
    username = forms.CharField(label='Логин',
                               widget=forms.TextInput(attrs={'class': 'forms-input'}))
    password = forms.CharField(label='Логин',
                               widget=forms.PasswordInput(attrs={'class': 'forms-input'}))