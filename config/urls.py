from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.sitemaps.views import sitemap
from domain.website import seo

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("domain.website.urls")),
    path("management/", include("domain.matchmaking.urls")),
    path("", include("domain.base.urls")),
    path("portal/", include("domain.portal.urls")),
    path("", include("domain.elite.urls")),

    path("robots.txt", seo.robots_txt),
       path("sitemap.xml", sitemap, {"sitemaps": seo.SITEMAPS}, name="django.contrib.sitemaps.views.sitemap"),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
