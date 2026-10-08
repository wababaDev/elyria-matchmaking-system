/* ================================================== */
/* OMBARA - MAIN.JS */
/* ================================================== */
/* TABLE OF CONTENTS
   ==================================================
   1. LENIS SMOOTH SCROLL INIT      | find: const lenis, function raf
   2. GLOBAL VARS & CACHED SELECTORS| find: preloaderHidden, $window, $document, $body
   3. PRELOADER                     | find: function hidePreloader
    4. HERO SLIDER INIT             | find: heroSwiper, swiperContainer, new Swiper
   5. FEATURE GALLERY SCROLL        | find: $featureGallerySection, featureGallerySlides
   5.1 Gallery Card Height/Anim     | find: syncFeatureGalleryCardHeight, animateFeatureGalleryCardContent
   5.2 Gallery Slide State          | find: setFeatureGallerySlide, formatFeatureGalleryIndex
   5.3 Gallery Scroll Progress      | find: updateFeatureGalleryScrollState, scrollFeatureGalleryTo
   5.4 Gallery Init                 | find: function initFeatureGalleryScroll
   6. DOCUMENT READY (MAIN)         | find: $(document).ready
   6.1 Header Show/Hide on Scroll   | find: updateHeaderState, lastHeaderScrollY
   6.2 Back-to-Top Progress         | find: updateToTopProgress, toTopBtn, toTopProgress
   6.3 Internal Anchor Scroll       | find: scrollToInternalTarget
   6.4 Hero Swiper Init             | find: heroSwiper, swiperContainer, new Swiper
   6.5 Hero Scroll Indicator Click  | find: .hero-scroll-indicator
   6.6 Facilities Tabs              | find: .fac-tabs-item
   6.7 Nav/Anchor Click Handlers    | find: .header-link, .header-register-btn, .hero-menu-link
   6.8 Back-to-Top Button Click     | find: #toTopBtn
   6.9 Room Showcase Video Loader   | find: .room-showcase, loadRoomPreview
   6.10 Register Form Submission    | find: .register-form, actionUrl, $.ajax
   6.11 Scroll Event Binding        | find: lenis.on('scroll'), $window.on('scroll')
   6.12 Testimonials Swiper Init    | find: .testimonials-swiper
   6.13 Blog Detail Swiper Init     | find: .blog-detail-swiper
   6.14 Bootstrap Tooltips Init     | find: [data-bs-toggle="tooltip"]
   6.15 Map Marker Hover/Click      | find: .map-marker
   7. REVEAL & PARALLAX ON SCROLL   | find: $revealElements, revealObserver, handleScrollEffects
   7.1 Reveal Visibility Check      | find: revealVisibleElements
   7.2 Hero Mask Clip-Path Scroll   | find: heroMask, clip-path
   7.3 Parallax Data-Speed Elements | find: $parallaxElements, data-speed
   8. WINDOW LOAD & PRELOADER FALLBACK | find: $(window).on('load'), setTimeout(hidePreloader
================================================== */

// Initialize Lenis Smooth Scroll
const lenis = typeof Lenis !== 'undefined'
    ? new Lenis({
        duration: 1.2,
        easing: (t) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
        direction: 'vertical',
        gestureDirection: 'vertical',
        smooth: true,
        mouseMultiplier: 1,
        smoothTouch: false,
        touchMultiplier: 2,
        infinite: false
    })
    : null;

function raf(time) {
    lenis?.raf(time);
    requestAnimationFrame(raf);
}

if (lenis) {
    requestAnimationFrame(raf);
}

let preloaderHidden = false;
const $window = $(window);
const $document = $(document);
const $body = $('body');

function hidePreloader() {
    const $preloader = $('#preloader');

    if (!$preloader.length || $preloader.hasClass('is-hidden')) {
        $body.removeClass('is-loading');
        return;
    }

    preloaderHidden = true;

    window.setTimeout(() => {
        $preloader.addClass('is-hidden');
        $body.removeClass('is-loading');

        window.setTimeout(() => {
            $preloader.remove();
        }, 900);
    }, 1500);
}

const $featureGallerySection = $('[data-feature-gallery-scroll]').first();
const featureGallerySection = $featureGallerySection.get(0);
const $featureGallerySlides = featureGallerySection
    ? $featureGallerySection.find('[data-feature-gallery-slide]')
    : $();
const featureGallerySlides = $featureGallerySlides.toArray();
const $featureGalleryInfos = featureGallerySection
    ? $featureGallerySection.find('[data-feature-gallery-info]')
    : $();
const featureGalleryInfos = $featureGalleryInfos.toArray();
const $featureGalleryCard = featureGallerySection
    ? $featureGallerySection.find('.feature-gallery-scroll__card').first()
    : $();
const featureGalleryCard = $featureGalleryCard.get(0);
const $featureGalleryCardEyebrow = $('#featureGalleryCardEyebrow');
const $featureGalleryCardTitle = $('#featureGalleryCardTitle');
const $featureGalleryCardImage = $('#featureGalleryCardImage');
const $featureGalleryCardText = $('#featureGalleryCardText');
const $featureGalleryCurrentIndex = $('#featureGalleryCurrentIndex');
const $featureGalleryTotalCount = $('#featureGalleryTotalCount');
const $featureGalleryProgressFill = $('#featureGalleryProgressFill');
const $featureGalleryPrevBtn = $('#featureGalleryPrevBtn');
const $featureGalleryNextBtn = $('#featureGalleryNextBtn');
const $featureGallerySkipBtn = $('#featureGallerySkipBtn');

let activeFeatureGalleryIndex = -1;
let featureGalleryCardResetTimer = 0;

function formatFeatureGalleryIndex(index) {
    return String(index + 1).padStart(2, '0');
}

function syncFeatureGalleryCardHeight() {
    if (featureGalleryCard) {
        $featureGalleryCard.css('height', `${featureGalleryCard.scrollHeight}px`);
    }
}

function animateFeatureGalleryCardContent(updateContent, shouldAnimate = true) {
    if (!featureGalleryCard) {
        updateContent();
        return;
    }

    const startHeight = featureGalleryCard.offsetHeight || featureGalleryCard.scrollHeight;
    $featureGalleryCard.css('height', `${startHeight}px`);
    $featureGalleryCard.removeClass('is-content-revealing');
    void featureGalleryCard.offsetHeight;

    if (featureGalleryCardResetTimer) {
        window.clearTimeout(featureGalleryCardResetTimer);
    }

    requestAnimationFrame(() => {
        if (shouldAnimate) {
            $featureGalleryCard.addClass('is-content-revealing');
        }

        updateContent();

        const nextHeight = featureGalleryCard.scrollHeight;
        requestAnimationFrame(() => {
            $featureGalleryCard.css('height', `${nextHeight}px`);
        });

        featureGalleryCardResetTimer = window.setTimeout(() => {
            $featureGalleryCard.removeClass('is-content-revealing').css('height', '');
        }, shouldAnimate ? 900 : 260);
    });
}

function setFeatureGallerySlide(index) {
    if (!featureGallerySlides.length || !featureGalleryInfos.length) {
        return;
    }

    const safeIndex = Math.max(0, Math.min(index, featureGallerySlides.length - 1));
    const activeSlide = featureGallerySlides[safeIndex];
    const activeInfo = featureGalleryInfos[safeIndex];
    const $activeSlide = activeSlide ? $(activeSlide) : $();
    const $activeInfo = activeInfo ? $(activeInfo) : $();
    const hasChanged = safeIndex !== activeFeatureGalleryIndex;

    activeFeatureGalleryIndex = safeIndex;

    featureGallerySlides.forEach((slide, slideIndex) => {
        const $slide = $(slide);
        if (slideIndex === safeIndex) {
            $slide.removeClass('is-leaving').addClass('is-active');
        } else if ($slide.hasClass('is-active')) {
            $slide.addClass('is-leaving').removeClass('is-active');
            setTimeout(() => {
                $slide.removeClass('is-leaving');
            }, 800);
        } else {
            $slide.removeClass('is-active is-leaving');
        }
    });

    animateFeatureGalleryCardContent(() => {
        if ($featureGalleryCardEyebrow.length && $activeInfo.length) {
            $featureGalleryCardEyebrow.text($activeInfo.attr('data-eyebrow') || '');
        }

        if ($featureGalleryCardTitle.length && $activeInfo.length) {
            $featureGalleryCardTitle.text($activeInfo.attr('data-title') || '');
        }

        if ($featureGalleryCardText.length && $activeInfo.length) {
            $featureGalleryCardText.text($activeInfo.attr('data-text') || '');
        }

        if ($featureGalleryCardImage.length && $activeSlide.length) {
            const $activeImage = $activeSlide.find('img').first();

            if ($activeImage.length) {
                $featureGalleryCardImage
                    .attr('src', $activeImage.attr('src') || '')
                    .attr('alt', $activeImage.attr('alt') || '');
            }
        }
    }, hasChanged);

    if ($featureGalleryCurrentIndex.length) {
        $featureGalleryCurrentIndex.text(formatFeatureGalleryIndex(safeIndex));
    }
}

function updateFeatureGalleryScrollState() {
    if (!featureGallerySection || !featureGallerySlides.length) {
        return;
    }

    const rect = featureGallerySection.getBoundingClientRect();
    const scrollDistance = Math.max(featureGallerySection.offsetHeight - window.innerHeight, 1);
    const scrolled = Math.min(Math.max(-rect.top, 0), scrollDistance);
    const progress = scrolled / scrollDistance;
    const maxIndex = Math.max(featureGallerySlides.length - 1, 1);
    const nextIndex = Math.min(featureGallerySlides.length - 1, Math.round(progress * maxIndex));

    if (nextIndex !== activeFeatureGalleryIndex) {
        setFeatureGallerySlide(nextIndex);
    }

    if ($featureGalleryProgressFill.length) {
        $featureGalleryProgressFill.css('transform', `scaleX(${progress})`);
    }
}

function scrollFeatureGalleryTo(index) {
    if (!featureGallerySection || !featureGallerySlides.length) {
        return;
    }

    const maxIndex = Math.max(featureGallerySlides.length - 1, 1);
    const safeIndex = Math.max(0, Math.min(index, maxIndex));
    const scrollDistance = Math.max(featureGallerySection.offsetHeight - window.innerHeight, 1);
    const absoluteTop = window.scrollY + featureGallerySection.getBoundingClientRect().top;

    if (lenis) {
        lenis.scrollTo(absoluteTop + (safeIndex / maxIndex) * scrollDistance, { duration: 1.2 });
    } else {
        $('html, body').stop().animate({ scrollTop: absoluteTop + (safeIndex / maxIndex) * scrollDistance }, 650);
    }
}

function initFeatureGalleryScroll() {
    if (!featureGallerySection || !featureGallerySlides.length || !featureGalleryInfos.length) {
        return;
    }

    if ($featureGalleryTotalCount.length) {
        $featureGalleryTotalCount.text(String(featureGallerySlides.length).padStart(2, '0'));
    }

    setFeatureGallerySlide(0);
    window.setTimeout(syncFeatureGalleryCardHeight, 40);

    if ($featureGalleryPrevBtn.length) {
        $featureGalleryPrevBtn.on('click', () => {
            scrollFeatureGalleryTo(activeFeatureGalleryIndex - 1);
        });
    }

    if ($featureGalleryNextBtn.length) {
        $featureGalleryNextBtn.on('click', () => {
            scrollFeatureGalleryTo(activeFeatureGalleryIndex + 1);
        });
    }

    if ($featureGallerySkipBtn.length) {
        $featureGallerySkipBtn.on('click', () => {
            const rect = featureGallerySection.getBoundingClientRect();
            const absoluteBottom = window.scrollY + rect.bottom;

            if (lenis) {
                lenis.scrollTo(absoluteBottom, { duration: 1.2, offset: 0 });
            } else {
                $('html, body').stop().animate({ scrollTop: absoluteBottom }, 650);
            }
        });
    }

    new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
            $featureGallerySection.toggleClass('is-out-of-view', !entry.isIntersecting);
        });
    }, { rootMargin: '100% 0px 100% 0px' }).observe(featureGallerySection);

    updateFeatureGalleryScrollState();
}

$(document).ready(function () {
    const $header = $('.header').first();
    const header = $header.get(0);
    const $footer = $('.footer').first();
    const footer = $footer.get(0);
    const $gallerySections = $('.feature-gallery-section');
    const $toTopBtn = $('#toTopBtn');
    const toTopBtn = $toTopBtn.get(0);
    const $toTopProgress = $('#toTopProgress');
    const toTopProgress = $toTopProgress.get(0);
    let lastHeaderScrollY = window.scrollY;

    function updateHeaderState(scrollY = window.scrollY) {
        if (!header) return;

        const delta = scrollY - lastHeaderScrollY;
        const $heroSection = $('#home');
        const heroHeight = $heroSection.length ? $heroSection.outerHeight() : window.innerHeight;
        const isInHero = scrollY < heroHeight * 0.7;

        if (isInHero) {
            $header.addClass('is-hidden');
        } else {
            const hideOnDirection = delta > 2;
            const showOnDirection = delta < -2;

            if (hideOnDirection) {
                $header.removeClass('is-hidden');
            } else if (showOnDirection) {
                $header.removeClass('is-hidden');
            }
        }

        const gallerySection = $('.feature-gallery-section').first().get(0);
        let isInGallery = false;
        if (gallerySection) {
            const rect = gallerySection.getBoundingClientRect();
            // Header should hide as long as the gallery section is taking up the screen
            isInGallery = rect.top <= 50 && rect.bottom >= window.innerHeight * 0.1;
        }

        if (isInHero || isInGallery) {
            $header.addClass('is-hidden').removeClass('scrolled');

            if (isInGallery) {
                $header.addClass('gallery-hidden');
            } else {
                $header.removeClass('gallery-hidden');
            }

            lastHeaderScrollY = scrollY;
            return;
        }

        $header.removeClass('is-hidden gallery-hidden');
        $header.toggleClass('scrolled', scrollY > 50);

        lastHeaderScrollY = scrollY;
    }

    function updateToTopProgress() {
        if (!toTopBtn || !toTopProgress) {
            return;
        }

        const scrollTop = window.scrollY;
        const scrollHeight = Math.max($document.height() - $window.height(), 0);
        const progress = scrollHeight > 0 ? Math.min(scrollTop / scrollHeight, 1) : 0;
        const viewportProbeTop = window.innerHeight * 0.35;
        const viewportProbeBottom = window.innerHeight * 0.65;
        const isOnGallery = $gallerySections.toArray().some((section) => {
            const rect = section.getBoundingClientRect();
            return rect.top <= viewportProbeBottom && rect.bottom >= viewportProbeTop;
        });

        $toTopProgress.css('height', `${progress * 100}%`);
        $toTopBtn.toggleClass('is-visible', scrollTop > window.innerHeight * 0.35);
        $toTopBtn.toggleClass('on-gallery', isOnGallery);
    }

    function scrollToInternalTarget(targetSelector) {
        if (!targetSelector || targetSelector === '#' || targetSelector === '#home') {
            if (lenis) {
                lenis.scrollTo(0, { duration: 1.1 });
            } else {
                $('html, body').stop().animate({ scrollTop: 0 }, 650);
            }
            return;
        }

        const $target = $(targetSelector).first();
        if (!$target.length) {
            return;
        }

        const targetTop = Math.max(0, ($target.offset()?.top || 0) - 24);

        if (lenis) {
            lenis.scrollTo(targetTop, { duration: 1.1 });
        } else {
            $('html, body').stop().animate({ scrollTop: targetTop }, 650);
        }
    }

    updateHeaderState();
    updateToTopProgress();

    $window.on('resize', function () {
        updateHeaderState(window.scrollY);
        updateToTopProgress();
        updateFeatureGalleryScrollState();
    });

    if (toTopBtn && footer) {
        const footerObserver = new IntersectionObserver((entries) => {
            entries.forEach((entry) => {
                $toTopBtn.toggleClass('on-footer', entry.isIntersecting);
            });
        }, {
            threshold: 0.15
        });

        footerObserver.observe(footer);
    }

    // === Initialize Hero Slider (If it exists) ===
    let heroSwiper;

    // Check if hero swiper exists in DOM (can be .hero-swiper or .hero-slider)
    const swiperContainer = $('.hero-swiper, .hero-slider').get(0);

    if (swiperContainer && typeof Swiper !== 'undefined') {
        heroSwiper = new Swiper(swiperContainer, {
            loop: true,
            speed: 3000,
            effect: 'fade',
            fadeEffect: {
                crossFade: true
            },
            autoplay: {
                delay: 5000,
                disableOnInteraction: false
            },
            navigation: {
                nextEl: '.swiper-next',
                prevEl: '.swiper-prev'
            },
            on: {
                autoplayTimeLeft(s, time, progress) {
                    $('.hero-nav-progress').css('width', (1 - progress) * 100 + '%');
                }
            }
        });

        $('.swiper-prev, .swiper-next').on('click', function () {
            heroSwiper.autoplay.resume();
        });
    }

    initFeatureGalleryScroll();

    $('.hero-scroll-indicator').on('click', function () {
        const $aboutSection = $('#about');
        const aboutSection = $aboutSection.get(0);
        if (aboutSection) {
            if (lenis) {
                lenis.scrollTo(aboutSection, { offset: -50 });
            } else {
                $('html, body').stop().animate({ scrollTop: ($aboutSection.offset()?.top || 0) - 50 }, 650);
            }
        }
    });

    $('.fac-tabs-item').on('click', function () {
        const target = $(this).data('target');
        $('.fac-tabs-item').removeClass('active');
        $('.fac-tab-pane').removeClass('active');
        $(this).addClass('active');
        $(target).addClass('active');
    });

    $('.header-link, .header-register-btn, .hero-menu-link, .hero-action-pill, .footer-link, .header-logo').on('click', function (event) {
        if ($(this).hasClass('dropdown-toggle')) {
            return;
        }

        const targetSelector = $(this).attr('href');

        if (!targetSelector || targetSelector === '#' || !targetSelector.startsWith('#')) {
            return;
        }

        event.preventDefault();
        scrollToInternalTarget(targetSelector);

        if ($('.navbar-collapse').hasClass('show')) {
            $('.navbar-toggler').trigger('click');
        }
    });

    $('#toTopBtn').on('click', function () {
        if (lenis) {
            lenis.scrollTo(0, { duration: 1.4 });
        } else {
            window.scrollTo({ top: 0, behavior: 'smooth' });
        }
    });

    $('.room-showcase').each(function () {
        const showcase = $(this);
        const media = showcase.find('.room-showcase-media');
        const trigger = showcase.find('.room-showcase-trigger');
        const panelButton = showcase.find('[data-load-room-preview]');
        const frame = showcase.find('.room-showcase-frame');

        function loadRoomPreview() {
            if (!media.length || !frame.length || media.hasClass('is-loaded')) {
                return;
            }

            let iframeSrc = trigger.attr('data-iframe-src');
            if (!iframeSrc) {
                return;
            }

            const origin = (window.location.origin && window.location.origin !== 'null')
                ? window.location.origin
                : 'http://localhost';

            iframeSrc += (iframeSrc.includes('?') ? '&' : '?')
                + 'autoplay=1&mute=0&enablejsapi=1&origin=' + encodeURIComponent(origin);

            frame.attr('src', iframeSrc);
            media.addClass('is-loaded');
        }

        trigger.on('click', function () {
            loadRoomPreview();
        });

        panelButton.on('click', function () {
            loadRoomPreview();
        });
    });

    $('.register-form').each(function () {
        const $form = $(this);

        if (!$form.find('.register-form-status').length) {
            $('<div class="register-form-status" aria-live="polite"></div>').appendTo($form);
        }
    });

    $('.register-form').on('submit', function (event) {
        // Real Django forms submit normally; only preview (data-demo) forms are handled here
        if (!this.hasAttribute('data-demo')) return;
        event.preventDefault();

        const $form = $(this);
        const formEl = $form.get(0);
        const $submitButton = $form.find('button[type="submit"]').first();
        const $status = $form.find('.register-form-status').first();
        const actionUrl = $form.attr('action') && $form.attr('action') !== '#'
            ? $form.attr('action')
            : 'contact-submit.php';
        const formData = $form.serializeArray();
        const pageName = window.location.pathname.split('/').pop() || 'index.html';
        const formLabel = $form.attr('data-form-label') || $submitButton.text().trim() || 'Website Form';
        const termsAccepted = $form.find('input[name="terms"]').is(':checked') ? 'Agreed' : 'Not agreed';
        const hasNewsletterField = $form.find('input[name="newsletter"]').length > 0;
        const newsletterValue = hasNewsletterField && $form.find('input[name="newsletter"]').is(':checked') ? 'Yes' : 'No';

        if (formEl && typeof formEl.reportValidity === 'function' && !formEl.reportValidity()) {
            return;
        }

        formData.push({ name: 'terms', value: termsAccepted });
        formData.push({ name: 'newsletter', value: newsletterValue });
        formData.push({ name: 'page_name', value: pageName });
        formData.push({ name: 'form_label', value: formLabel });

        $status
            .removeClass('is-success is-error')
            .addClass('is-visible is-loading')
            .html('Submitting your enquiry...');

        $submitButton.prop('disabled', true);

        $.ajax({
            url: actionUrl,
            method: 'POST',
            data: $.param(formData),
            dataType: 'json',
            headers: {
                Accept: 'application/json'
            }
        }).done(function (response) {
            if (!response || response.success !== true) {
                $status
                    .removeClass('is-loading is-success')
                    .addClass('is-error')
                    .html(response && response.message ? response.message : 'Unable to submit your enquiry right now.');
                return;
            }

            if (formEl) {
                formEl.reset();
            }

            $status
                .removeClass('is-loading is-error')
                .addClass('is-success')
                .html(response.message || 'Thank you. Your enquiry has been sent successfully.');
        }).fail(function (xhr) {
            let message = 'Unable to submit your enquiry right now.';

            if (xhr.responseJSON && xhr.responseJSON.message) {
                message = xhr.responseJSON.message;
            }

            $status
                .removeClass('is-loading is-success')
                .addClass('is-error')
                .html(message);
        }).always(function () {
            $submitButton.prop('disabled', false);
        });
    });

    if (lenis) {
        lenis.on('scroll', function (event) {
            const scrollY = typeof event?.scroll === 'number' ? event.scroll : window.scrollY;
            updateHeaderState(scrollY);
            updateToTopProgress();
            updateFeatureGalleryScrollState();
        });
    } else {
        $window.on('scroll', function () {
            const scrollY = window.scrollY;
            updateHeaderState(scrollY);
            updateToTopProgress();
            updateFeatureGalleryScrollState();
        });
    }

    // ==========================================
    // Initialize Testimonials Swiper
    // ==========================================
    if ($('.testimonials-swiper').length) {
        new Swiper('.testimonials-swiper', {
            slidesPerView: 1,
            spaceBetween: 20,
            loop: true,
            autoplay: {
                delay: 5000,
                disableOnInteraction: false,
            },
            pagination: {
                el: '.swiper-pagination',
                clickable: true,
            },
            breakpoints: {
                768: {
                    slidesPerView: 2,
                    spaceBetween: 30,
                }
            }
        });
    }

    // ==========================================
    // Initialize Blog Detail Swipers
    // ==========================================
    if (typeof Swiper !== 'undefined') {
        $('.blog-detail-swiper').each(function () {
            const swiperEl = this;
            const $swiperEl = $(swiperEl);
            const paginationEl = $swiperEl.find('.swiper-pagination').get(0);
            const nextEl = $swiperEl.find('.swiper-button-next').get(0);
            const prevEl = $swiperEl.find('.swiper-button-prev').get(0);

            new Swiper(swiperEl, {
                slidesPerView: 1,
                spaceBetween: 0,
                loop: true,
                speed: 900,
                autoplay: {
                    delay: 4200,
                    disableOnInteraction: false,
                },
                pagination: paginationEl ? {
                    el: paginationEl,
                    clickable: true,
                } : undefined,
                navigation: nextEl && prevEl ? {
                    nextEl,
                    prevEl,
                } : undefined,
            });
        });
    }

    // ==========================================
    // Initialize Bootstrap Tooltips
    // ==========================================
    $('[data-bs-toggle="tooltip"]').toArray().map((tooltipTriggerEl) => new bootstrap.Tooltip(tooltipTriggerEl, {
        container: 'body',
        trigger: 'hover focus click'
    }));

    // Interactive Map Markers Hover Effect
    $('.map-marker').on('mouseenter', function () {
        $(this).css('transform', 'scale(1.15)');
    }).on('mouseleave', function () {
        $(this).css('transform', 'scale(1)');
    });

    // Prevent tooltip from getting stuck on mobile after click
    $('.map-marker').on('click', function (e) {
        e.preventDefault();
        $(this).tooltip('toggle');
    });
});

$(function () {
    const $revealElements = $('.reveal');
    const revealElements = $revealElements.toArray();
    const $heroMask = $('.hero-mask').first();
    const heroMask = $heroMask.get(0);
    const $parallaxElements = $('[data-speed]');
    const revealVisibleElements = () => {
        $revealElements.each(function () {
            const el = this;
            const rect = el.getBoundingClientRect();
            const isInViewport = rect.top <= window.innerHeight * 0.95 && rect.bottom >= window.innerHeight * 0.05;

            if (isInViewport) {
                $(el).addClass('is-visible');
            }
        });
    };

    const revealObserver = new IntersectionObserver((entries, observer) => {
        entries.forEach((entry) => {
            if (entry.isIntersecting) {
                $(entry.target).addClass('is-visible');
                observer.unobserve(entry.target);
            }
        });
    }, {
        threshold: 0.15,
        rootMargin: '0px 0px -50px 0px'
    });

    revealElements.forEach((el) => revealObserver.observe(el));
    revealVisibleElements();

    const handleScrollEffects = (scrollY = window.scrollY) => {
        if (heroMask) {
            const scrollDistance = window.innerHeight * 0.9;
            if (scrollY <= 0) {
                $heroMask.css('clip-path', 'inset(0% 0% 0% 0%)');
            } else if (scrollY < scrollDistance) {
                const progress = scrollY / scrollDistance;
                const eased = Math.pow(progress, 0.9);
                const insetV = 20 * eased;
                const insetH = 3 * eased;
                $heroMask.css('clip-path', `inset(${insetV}% ${insetH}% ${insetV}% ${insetH}%)`);
            } else {
                $heroMask.css('clip-path', 'inset(20% 3% 20% 3%)');
            }
        }

        $parallaxElements.each(function () {
            const $el = $(this);
            const el = this;
            const speed = parseFloat($el.attr('data-speed'));
            const rect = el.getBoundingClientRect();
            const viewportCenter = window.innerHeight / 2;
            const elementCenter = rect.top + (rect.height / 2);
            const distanceFromCenter = elementCenter - viewportCenter;
            const maxOffset = Math.max(28, rect.height * 0.08);
            const yPos = Math.max(
                -maxOffset,
                Math.min(maxOffset, -distanceFromCenter * (speed - 1) * 0.45)
            );
            const scale = Math.max(1.12, 1 + ((speed - 1) * 2.4));

            $el.css('--parallax-offset', `${yPos}px`);
            $el.css('--parallax-scale', scale.toFixed(3));
        });
    };

    handleScrollEffects();
    window.requestAnimationFrame(revealVisibleElements);
    window.setTimeout(revealVisibleElements, 160);

    if (lenis) {
        lenis.on('scroll', (event) => {
            handleScrollEffects(typeof event?.scroll === 'number' ? event.scroll : window.scrollY);
            revealVisibleElements();
        });
    } else {
        $window.on('scroll', () => {
            handleScrollEffects();
            revealVisibleElements();
        });
    }

    $window.on('resize', () => {
        handleScrollEffects();
        revealVisibleElements();
    });
});

$(window).on('load', () => {
    hidePreloader();
});

window.setTimeout(() => {
    hidePreloader();
}, 3200);
