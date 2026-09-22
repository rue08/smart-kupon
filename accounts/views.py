from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import firebase
from .authentication import extract_bearer_token
from .models import User
from .serializers import UserSerializer


class FirebaseLoginView(APIView):
    """POST /api/v1/auth/firebase/login

    Verifies the Firebase ID token in Authorization: Bearer <token>, then
    creates (first sign-in) or returns (subsequent sign-in) the matching
    local User row -- the bootstrap step FR-1.1-FR-1.3 describes as
    "verify a Firebase ID token and create/return the local user profile."
    """

    authentication_classes = []  # verifies the token itself; a local User may not exist yet
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            token = extract_bearer_token(request)
        except AuthenticationFailed as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_401_UNAUTHORIZED)
        if token is None:
            return Response(
                {'detail': 'Authorization header must be "Bearer <token>".'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        try:
            decoded = firebase.verify_id_token(token)
        except firebase.TokenVerificationError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_401_UNAUTHORIZED)

        uid = decoded['uid']
        email = decoded.get('email', '')
        name = decoded.get('name', '') or email.split('@')[0]

        user, created = User.objects.get_or_create(
            auth_provider_ref=uid,
            defaults={'name': name, 'email': email},
        )

        http_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(UserSerializer(user).data, status=http_status)


class MeView(APIView):
    """GET /api/v1/auth/me -- the authenticated user's own profile."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)
