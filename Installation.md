# Fresh install

## 1. Install required dependencies

Ensure you have `git`, `python` (version 3) and `pip` installed.

The installation process for this is OS dependant, please consult your OS manual for further help with this.

You may check the versions by running:

`python --version` and `pip --version` respectivly.

Depending on the OS you chose, python 3 might be under the `python3` name. If so, replace all occurances of `python` with `python3` in this README.

## 2. Downloading OpenBench

`git clone https://github.com/AndyGrant/OpenBench.git`

## 3. Installing required python packages

Once cloned, `cd` into the directory you cloned OpenBench to and run the following:

`pip install -r requirements.txt`

## 4. Changing secret (IMPORTANT)

Open `your_install_dir/OpenSite/settings.py` and navigate to the `SECRET_KEY` field on line 22.

Change the value of this key to something else, this is used to provide cryptographic signing, and should be set to a unique, unpredictable value.

The secret key must be a large random value and it must be kept secret.

While you're here, you might want to change the `DEBUG` variable to `False` if this a production install.

## 5. Creating the initial sqlite database

`python manage.py makemigrations OpenBench && python manage.py migrate`

## 6. Creating a superuser for django admin area

`python manage.py createsuperuser`

## 7. Starting the server

`python manage.py runserver`

## 8. Creating a user

Navigate to [http://localhost:8000/register/](http://localhost:8000/register/) and follow the steps on screen.

## 9. Activate user

Navigate to [http://localhost:8000/admin/](http://localhost:8000/admin/) and log in with the credentials you set for your superuser earlier.

Press the "Users" row under the "AUTHENTICATION AND AUTHORIZATION" group.

Then, press your user you created on step 8 and give it all permissions prefixed with "OpenBench" and press save.

Now, log out and navigate to the index page.

You may now log in as the user you created and use OpenBench!

# Further configuration

## Setting allowed hosts.

This setting is required to protect your site against some CSRF attacks, therefor it's important to set this to the domain you're using for OpenBench.

## Reverse Proxy

It is recommended to run OpenBench behind a reverse proxy, such as NGINX, Caddy or HAProxy to aid security as well as provide SSL for your installation. By using SSL you are not sending your credentials over plain text (which is a huge no-no)

If you're running the reverse proxy local on the same machine as OpenBench you only have to change the `ALLOWED_HOSTS` line as mentioned earlier to the public facing domain.

If you're instead running the proxy on another machine you will need to change the IP the Django server listens on. This can be done by instead of running the server with `python manage.py runserver`, running the server with `python manage.py runserver 0.0.0.0:8000`. Of course, you can change 0.0.0.0 to the IP you want OpenBench to run on, 0.0.0.0 works for most cases.
