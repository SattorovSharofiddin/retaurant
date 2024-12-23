from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from django.shortcuts import get_object_or_404
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework.exceptions import ValidationError
from rest_framework.fields import CharField, EmailField, IntegerField, HiddenField, CurrentUserDefault
from rest_framework.serializers import ModelSerializer, Serializer

from apps.models import Product, Order, Customer, Category
from apps.models_mongodb import RealTimeOrder


class ProductModelSerializer(ModelSerializer):
    class Meta:
        model = Product
        fields = ('id', 'name', 'price', 'category_id')


class OrderModelSerializer(ModelSerializer):
    customer = HiddenField(default=CurrentUserDefault())

    class Meta:
        model = Order
        fields = ('customer', 'products', 'created_at', 'updated_at')

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['products'] = ProductModelSerializer(instance.products.all(), many=True).data
        data['total_price'] = sum([product.price for product in instance.products.all()])
        return data


class CategoryModelSerializer(ModelSerializer):
    products = ProductModelSerializer(many=True, read_only=True)

    class Meta:
        model = Category
        fields = ('name', 'products')


class UserRegisterSerializer(ModelSerializer):
    full_name = CharField(write_only=True, max_length=250)
    password = CharField(write_only=True, max_length=250)
    confirm_password = CharField(write_only=True, max_length=250)

    class Meta:
        model = Customer
        fields = ('full_name', 'email', 'password', 'confirm_password')

    def validate(self, data):
        if Customer.objects.filter(email=data['email']).exists():
            raise ValidationError('This email already exist')
        elif not data['email'].endswith('@gmail.com'):
            raise ValidationError('please enter valid email')
        elif data['password'] != data['confirm_password']:
            raise ValidationError("Passwords do not match.")
        elif len(data['password']) < 8:
            raise ValidationError("Password must be 8")
        return data

    def create(self, validated_data):
        validated_data.pop('confirm_password')
        user = Customer.objects.create_user(**validated_data)
        return user


class SendVerificationEmailSerializer(Serializer):
    email = EmailField(write_only=True)


class VerifyEmailSerializer(Serializer):
    email = EmailField(write_only=True)
    code = IntegerField(write_only=True)

    def validate(self, data):
        email = data['email']
        code = data['code']
        user = Customer.objects.get(email=email)
        cache_user_id = cache.get(user.id)
        if user.is_active or code != cache_user_id:
            cache.delete(user.id)
            raise ValidationError("Invalid code.")
        return data

    def create(self, validated_data):
        email = validated_data['email']
        user = Customer.objects.get(email=email)
        user.is_active = True
        user.save()
        return user


class SendPasswordResetLinkSerializer(Serializer):
    email = EmailField(write_only=True)

    def validate(self, data):
        email = data['email']
        user = get_object_or_404(Customer, email=email)
        if not user.is_active:
            raise ValidationError("User is not active.")
        data['full_name'] = user.full_name
        data['pk'] = user.pk
        data['token'] = default_token_generator.make_token(user)
        return data

    def create(self, validated_data):
        return validated_data


class CheckPasswordResetTokenSerializer(Serializer):
    uid = CharField(write_only=True)
    token = CharField(write_only=True)

    def validate(self, data):
        pk = force_str(urlsafe_base64_decode(data['uid']))
        if not pk.isdigit():
            raise ValidationError("Invalid User uid")
        token = data['token']
        user = get_object_or_404(Customer, pk=pk)
        if not default_token_generator.check_token(user, token):
            raise ValidationError("Invalid token.")
        return data


class PasswordResetSerializer(Serializer):
    uid = CharField(write_only=True)
    token = CharField(write_only=True)
    password = CharField(write_only=True)
    confirm_password = CharField(write_only=True)

    def validate(self, data):
        token = data['token']
        pk = force_str(urlsafe_base64_decode(data['uid']))
        data['pk'] = pk
        user = get_object_or_404(Customer, pk=pk)
        if data['password'] != data['confirm_password']:
            raise ValidationError("Passwords do not match.")
        if not pk.isdigit():
            raise ValidationError("Invalid User uid")
        if not user.is_active:
            raise ValidationError("User is not active.")
        if not default_token_generator.check_token(user, token):
            raise ValidationError("Invalid token.")
        return data

    def create(self, validated_data):
        validated_data.pop('confirm_password')
        user = get_object_or_404(Customer, pk=validated_data['pk'])
        user.set_password(validated_data['password'])
        user.save()
        return user


class RealTimeOrderModelSerializer(ModelSerializer):
    class Meta:
        model = RealTimeOrder
        fields = ['order_id', 'customer_name', 'total_price', 'products', 'create_at']
