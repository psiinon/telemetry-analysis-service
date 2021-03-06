# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
import requests
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.oauth2.views import (OAuth2CallbackView,
                                                          OAuth2LoginView)
from django.core.exceptions import PermissionDenied

from .provider import AtmoGoogleProvider

#: URL endpoint to fetch the Google OpenID Connect discovery document from
DISCOVERY_DOCUMENT_ENDPOINT = 'https://accounts.google.com/.well-known/openid-configuration'
#: URL to verify Google OpenID Connect tokens against during verification.
TOKENINFO_ENDPOINT = 'https://www.googleapis.com/oauth2/v3/tokeninfo'


class AtmoGoogleOAuth2Adapter(GoogleOAuth2Adapter):
    provider_id = AtmoGoogleProvider.id

    def discovery_document(self):
        "Fetch the discovery document from Google."
        response = requests.get(DISCOVERY_DOCUMENT_ENDPOINT)
        response.raise_for_status()
        return response.json()

    def get_url(self, name, default=None):
        "Fetch the discovery document for the given URL endpoint name."
        return self.discovery_document().get(name, default)

    @property
    def access_token_url(self):
        "Get the access token URL from the Google discovery document."
        return self.get_url('token_endpoint', super().access_token_url)

    @property
    def authorize_url(self):
        "Get the authorization endpoint URL from the Google discovery document."
        return self.get_url('authorization_endpoint', super().authorize_url)

    @property
    def profile_url(self):
        "Get the user profile URL from the Google discovery document."
        return self.get_url('userinfo_endpoint', super().profile_url)

    def complete_login(self, request, app, token, **kwargs):
        """
        Extend the default login completion by verification of response data
        as documented on:

          https://developers.google.com/identity/protocols/OpenIDConnect

        This is an important part of the user verification during login.
        """
        response = kwargs.get('response', None)
        if response is None:
            raise PermissionDenied('Something went wrong during the login')

        # response contains data from the access token URL request
        id_token = response.get('id_token', None)
        if id_token is None:
            raise PermissionDenied('No ID received from Google')

        # verify the ID token using Google's endpoint
        response = requests.post(TOKENINFO_ENDPOINT, data={'id_token': id_token})
        response.raise_for_status()
        id_token_data = response.json()

        # verify the received audience token with the client ID we have
        provider = self.get_provider()
        if provider.get_app(request).client_id != id_token_data.get('aud', None):
            raise PermissionDenied('Invalid client ID received')

        # if configured, check if the return hosted domain matches what we have
        hosted_domain = provider.get_hosted_domain()
        if hosted_domain and hosted_domain != id_token_data.get('hd', None):
            raise PermissionDenied('Access restricted to users of '
                                   'the domain %s' % hosted_domain)

        return super().complete_login(request, app, token, **kwargs)


oauth2_login = OAuth2LoginView.adapter_view(AtmoGoogleOAuth2Adapter)
oauth2_callback = OAuth2CallbackView.adapter_view(AtmoGoogleOAuth2Adapter)
