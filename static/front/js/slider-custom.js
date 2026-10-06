$(function () {
    const $bg1 = $('#hero-main-bg-1');
    const $bg2 = $('#hero-main-bg-2');
    const $miniCards = $('.ticker-track .hero-mini-card img');

    if (!$bg1.length || !$bg2.length || !$miniCards.length) {
        return;
    }

    const uniqueImages = [...new Set($miniCards.map(function () {
        return $(this).attr('src');
    }).get())];

    let currentIndex = 0;
    let slideInterval;
    let activeBg = 1;

    function getActiveSource() {
        return activeBg === 1 ? $bg1.attr('src') : $bg2.attr('src');
    }

    function changeMainImage(src) {
        if (activeBg === 1) {
            $bg2.attr('src', src).removeClass('opacity-0').addClass('opacity-100');
            $bg1.removeClass('opacity-100').addClass('opacity-0');
            activeBg = 2;
        } else {
            $bg1.attr('src', src).removeClass('opacity-0').addClass('opacity-100');
            $bg2.removeClass('opacity-100').addClass('opacity-0');
            activeBg = 1;
        }
    }

    function nextSlide() {
        currentIndex = (currentIndex + 1) % uniqueImages.length;
        changeMainImage(uniqueImages[currentIndex]);
    }

    function startSlideshow() {
        stopSlideshow();
        slideInterval = window.setInterval(nextSlide, 4000);
    }

    function stopSlideshow() {
        window.clearInterval(slideInterval);
    }

    $miniCards.parent().css('cursor', 'pointer');

    $miniCards.on('click', function () {
        const src = $(this).attr('src');

        stopSlideshow();

        if (src === getActiveSource()) {
            startSlideshow();
            return;
        }

        currentIndex = uniqueImages.indexOf(src);
        changeMainImage(src);
        startSlideshow();
    });

    startSlideshow();
});
