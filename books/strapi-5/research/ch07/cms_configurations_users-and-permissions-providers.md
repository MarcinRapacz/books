# Users & Permissions Providers

> Source: https://docs.strapi.io/cms/configurations/users-and-permissions-providers

Configure OAuth and OAuth2 providers for Strapi's Users & Permissions authentication feature, with setup guides for common providers like GitHub, Google, and Auth0, plus instructions for creating custom providers.

Strapi comes with a predefined set of built-in providers for the [Users & Permissions feature](/cms/features/users-permissions). The present page explains how the login flow works, how to set up the server URL, and list many examples for common 3rd-party providers.

If you're looking to create your own custom provider, please refer to the [dedicated guide](/cms/configurations/users-and-permissions-providers/new-provider-guide).

## Understanding the login flow

[Grant](https://github.com/simov/grant) and [Purest](https://github.com/simov/purest) allow you to use OAuth and OAuth2 providers to enable authentication in your application.

For a better understanding, review the following description of the login flow. The example uses `github` as the provider but it works the same for other providers.

Let's say that:
* Strapi's backend is located at: `strapi.website.com`, and
* Your app frontend is located at: `website.com`

1. The user goes on your frontend app (`https://website.com`) and clicks on your button `connect with Github`.
2. The frontend redirects the tab to the backend URL: `https://strapi.website.com/api/connect/github`.
3. The backend redirects the tab to the GitHub login page where the user logs in.
4. Once done, Github redirects the tab to the backend URL:`https://strapi.website.com/api/connect/github/callback?code=abcdef`.
5. The backend uses the given `code` to get an `access_token` from Github that can be used for a period of time to make authorized requests to Github to get the user info.
6. Then, the backend redirects the tab to the url of your choice with the param `access_token` (example: `http://website.com/connect/github/redirect?access_token=eyfvg`).
7. The frontend (`http://website.com/connect/github/redirect`) calls the backend with `https://strapi.website.com/api/auth/github/callback?access_token=eyfvg` that returns the Strapi user profile with its `jwt`. <br/> (Under the hood, the backend asks Github for the user's profile and a match is done on Github user's email address and Strapi user's email address).
8. The frontend now possesses the user's `jwt`, which means the user is connected and the frontend can make authenticated requests to the backend!

An example of a frontend app that handles this flow can be found here: [react login example application](https://github.com/strapi/strapi-examples/tree/master/examples/login-react).

## Setting up the server URL

Before setting up a provider you must specify the absolute URL of your backend in `/config/server`:

```js title="/config/server.js"
module.exports = ({ env }) => ({
  host: env('HOST', '0.0.0.0'),
  port: env.int('PORT', 1337),
  url: env('', 'http://localhost:1337'),
});
```

```ts title="/config/server.ts"

  host: env('HOST', '0.0.0.0'),
  port: env.int('PORT', 1337),
  url: env('', 'http://localhost:1337'),
});
```

:::tip
Later you will give this URL to your provider. <br/> For development, some providers accept the use of localhost urls but many don't. In this case we recommend to use [ngrok](https://ngrok.com/docs) (`ngrok http 1337`) that will make a proxy tunnel from a url it created to your localhost url (e.g., `url: env('', 'https://5299e8514242.ngrok.io'),`).
:::

## Setting up the provider - Examples

Instead of a generic explanation we decided to show an example for each provider. You can also [create your own custom provider](/cms/configurations/users-and-permissions-providers/new-provider-guide).

In the following examples, the frontend application will be the [react login example application](https://github.com/strapi/strapi-examples/tree/master/examples/login-react)  running on `http://localhost:3000`, while Strapi (i.e., the backend server) will be running on `http://localhost:1337`.

- [Auth0](/cms/configurations/users-and-permissions-providers/auth-zero): Configure authentication through the Users & Permissions feature with Auth0.
- [AWS Cognito](/cms/configurations/users-and-permissions-providers/aws-cognito): Configure authentication through the Users & Permissions feature with AWS Cognito.
- [CAS](/cms/configurations/users-and-permissions-providers/cas): Configure authentication through the Users & Permissions feature with CAS.
- [Discord](/cms/configurations/users-and-permissions-providers/discord): Configure authentication through the Users & Permissions feature with Discord.
- [Facebook](/cms/configurations/users-and-permissions-providers/facebook): Configure authentication through the Users & Permissions feature with Facebook.
- [GitHub](/cms/configurations/users-and-permissions-providers/github): Configure authentication through the Users & Permissions feature with GitHub.
- [Google](/cms/configurations/users-and-permissions-providers/google): Configure authentication through the Users & Permissions feature with Google.
- [Instagram](/cms/configurations/users-and-permissions-providers/instagram): Configure authentication through the Users & Permissions feature with Instagram.
- [Keycloak](/cms/configurations/users-and-permissions-providers/keycloak): Configure authentication through the Users & Permissions feature with Keycloak.
- [LinkedIn](/cms/configurations/users-and-permissions-providers/linkedin): Configure authentication through the Users & Permissions feature with LinkedIn.
- [Patreon](/cms/configurations/users-and-permissions-providers/patreon): Configure authentication through the Users & Permissions feature with Patreon.
- [Reddit](/cms/configurations/users-and-permissions-providers/reddit): Configure authentication through the Users & Permissions feature with Reddit.
- [Twitch](/cms/configurations/users-and-permissions-providers/twitch): Configure authentication through the Users & Permissions feature with Twitch.
- [Twitter](/cms/configurations/users-and-permissions-providers/twitter): Configure authentication through the Users & Permissions feature with Twitter.
- [VK](/cms/configurations/users-and-permissions-providers/vk): Configure authentication through the Users & Permissions feature with VK.

If you want to create and add a new custom provider, please refer to the following guide:

- [Custom provider guide](/cms/configurations/users-and-permissions-providers/new-provider-guide): Learn how to create a custom Users & Permissions provider and add it to your Strapi application
