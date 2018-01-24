# django-developer-panel
![Django Developer Panel Interface](https://hirelofty-prod.s3.amazonaws.com/media/images/Screen_Shot_2017-05-12_at_5.20.30_PM.original.png)

## Installation

Install this module with pip:

    pip install django-developer-panel

Add the Developer Panel middleware to your application's `settings.py` and make sure `DEBUG` is enabled:

    DEBUG = True

    MIDDLEWARE = [
        'djdev_panel.middleware.DebugMiddleware',  # <--- this guy
        'django.middleware.security.SecurityMiddleware',
        'django.contrib.sessions.middleware.SessionMiddleware',
        'django.middleware.common.CommonMiddleware',
        'django.middleware.csrf.CsrfViewMiddleware',
        'django.contrib.auth.middleware.AuthenticationMiddleware',
        'django.contrib.messages.middleware.MessageMiddleware',
        'django.middleware.clickjacking.XFrameOptionsMiddleware',
    ]

You're ready to go.  Install the [Chrome plugin](https://github.com/loftylabs/djdevpanel-devtools) and get started!
