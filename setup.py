from setuptools import setup, find_packages

from flexibee_backend.version import get_version

setup(
    name='django-flexibee-backend',
    version=get_version(),
    description="Flexibee rest ORM backend.",
    keywords='django, REST, DB backend',
    author='Lubos Matl',
    author_email='matllubos@gmail.com',
    url='https://github.com/matllubos/django-flexibee-backend',
    license='LGPL',
    package_dir={'flexibee_backend': 'flexibee_backend'},
    include_package_data=True,
    packages=find_packages(),
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Web Environment',
        'Framework :: Django',
        'Intended Audience :: Developers',
        'Intended Audience :: End Users/Desktop',
        'License :: OSI Approved :: GNU LESSER GENERAL PUBLIC LICENSE (LGPL)',
        'Natural Language :: Czech',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
        'Topic :: Internet :: WWW/HTTP :: Site Management',
    ],
    install_requires=[
        'django>=1.6',
        'djangotoolbox>=1.6.2',
        'requests>=2.2.1',
    ],
    zip_safe=False
)
