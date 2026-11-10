/**
 * Index Page Slideshow Controller - Farmer Slot Booking System
 * Handles "How It Works" tutorial carousel:
 * - Next / Prev navigation with circular looping
 * - Clickable dots & top progress bar
 * - Auto-advance every 6s with pause on hover, keyboard focus, touch swipe, or hidden tab
 * - Accessible ARIA labels, polite live region announcements on manual navigation
 * - Keyboard (Left/Right/Home/End) and touch swipe gestures
 * - Respects prefers-reduced-motion
 */

document.addEventListener("DOMContentLoaded", () => {
  const card = document.getElementById("hiw-carousel");
  if (!card) return;

  // Progressive enhancement: add interactive styling class
  card.classList.add("hiw-interactive");

  const slides = Array.from(card.querySelectorAll(".hiw-slide"));
  const dots = Array.from(card.querySelectorAll(".hiw-dot"));
  const progressBar = card.querySelector(".hiw-progress-bar");
  const prevBtn = card.querySelector(".hiw-prev-btn");
  const nextBtn = card.querySelector(".hiw-next-btn");
  const playPauseBtn = card.querySelector(".hiw-play-pause-btn");
  const playPauseIcon = card.querySelector(".hiw-play-pause-icon");
  const playPauseLabel = card.querySelector(".hiw-play-pause-label");
  const liveRegion = document.getElementById("hiw-live-announcement");

  const totalSlides = slides.length;
  if (totalSlides === 0) return;

  const INTERVAL_MS = 6000;
  let currentIndex = 0;
  let timer = null;

  // Reduced motion detection
  const reducedMotionMedia = window.matchMedia("(prefers-reduced-motion: reduce)");
  let prefersReducedMotion = reducedMotionMedia.matches;

  // State flags for pausing
  let userPaused = prefersReducedMotion;
  let isHovered = false;
  let isFocused = false;
  let isTouching = false;

  // Touch coordinates
  let touchStartX = 0;
  let touchStartY = 0;

  // Update slide focusability for accessibility
  function updateSlideFocusability(slide, isCurrent) {
    slide.setAttribute("aria-hidden", isCurrent ? "false" : "true");
    const interactiveElements = slide.querySelectorAll("a, button, input, select, textarea, [tabindex]");
    interactiveElements.forEach((el) => {
      if (isCurrent) {
        el.removeAttribute("tabindex");
      } else {
        el.setAttribute("tabindex", "-1");
      }
    });
  }

  // Go to slide
  function goToSlide(targetIndex, manual = false) {
    const prevIndex = currentIndex;
    currentIndex = ((targetIndex % totalSlides) + totalSlides) % totalSlides;

    slides.forEach((slide, idx) => {
      slide.classList.remove("hiw-active", "hiw-prev-slide");
      if (idx === currentIndex) {
        slide.classList.add("hiw-active");
        updateSlideFocusability(slide, true);
      } else {
        if (idx === prevIndex) {
          slide.classList.add("hiw-prev-slide");
        }
        updateSlideFocusability(slide, false);
      }
    });

    // Update dots
    dots.forEach((dot, idx) => {
      const isSelected = idx === currentIndex;
      dot.classList.toggle("hiw-active", isSelected);
      dot.setAttribute("aria-selected", isSelected ? "true" : "false");
      dot.setAttribute("tabindex", isSelected ? "0" : "-1");
    });

    // Update progress bar
    if (progressBar) {
      const percent = ((currentIndex + 1) / totalSlides) * 100;
      progressBar.style.width = `${percent}%`;
    }

    // Screen reader announcement on manual navigation only
    if (manual && liveRegion) {
      const activeTitle = slides[currentIndex].querySelector(".hiw-slide-title")?.textContent?.trim() || "";
      liveRegion.textContent = `Step ${currentIndex + 1} of ${totalSlides}: ${activeTitle}`;
    }
  }

  // Auto-advance timer management
  function stopTimer() {
    if (timer) {
      clearInterval(timer);
      timer = null;
    }
  }

  function startTimer() {
    stopTimer();
    if (userPaused || prefersReducedMotion || isHovered || isFocused || isTouching || document.hidden) {
      return;
    }
    timer = setInterval(() => {
      goToSlide(currentIndex + 1, false);
    }, INTERVAL_MS);
  }

  function restartTimer() {
    stopTimer();
    if (!userPaused) {
      startTimer();
    }
  }

  // Toggle Play / Pause
  function setPlayPauseState(playing) {
    userPaused = !playing;
    if (playPauseIcon) {
      playPauseIcon.textContent = playing ? "⏸" : "▶";
    }
    if (playPauseLabel) {
      playPauseLabel.textContent = playing ? "Pause" : "Play";
    }
    if (playPauseBtn) {
      playPauseBtn.setAttribute("aria-label", playing ? "Pause slideshow autoplay" : "Start slideshow autoplay");
    }
    if (playing) {
      startTimer();
    } else {
      stopTimer();
    }
  }

  if (playPauseBtn) {
    playPauseBtn.addEventListener("click", () => {
      setPlayPauseState(userPaused);
    });
  }

  // Next / Prev button events
  if (prevBtn) {
    prevBtn.addEventListener("click", () => {
      goToSlide(currentIndex - 1, true);
      restartTimer();
    });
  }

  if (nextBtn) {
    nextBtn.addEventListener("click", () => {
      goToSlide(currentIndex + 1, true);
      restartTimer();
    });
  }

  // Dot button events
  dots.forEach((dot, idx) => {
    dot.addEventListener("click", () => {
      goToSlide(idx, true);
      restartTimer();
    });
  });

  // Pause on hover
  card.addEventListener("mouseenter", () => {
    isHovered = true;
    stopTimer();
  });

  card.addEventListener("mouseleave", () => {
    isHovered = false;
    startTimer();
  });

  // Pause on keyboard focus inside card
  card.addEventListener("focusin", () => {
    isFocused = true;
    stopTimer();
  });

  card.addEventListener("focusout", (e) => {
    if (!card.contains(e.relatedTarget)) {
      isFocused = false;
      startTimer();
    }
  });

  // Pause when browser tab is inactive / hidden
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      stopTimer();
    } else {
      startTimer();
    }
  });

  // Keyboard navigation when carousel or its controls have focus
  card.addEventListener("keydown", (e) => {
    if (e.key === "ArrowLeft") {
      e.preventDefault();
      goToSlide(currentIndex - 1, true);
      restartTimer();
    } else if (e.key === "ArrowRight") {
      e.preventDefault();
      goToSlide(currentIndex + 1, true);
      restartTimer();
    } else if (e.key === "Home") {
      e.preventDefault();
      goToSlide(0, true);
      restartTimer();
    } else if (e.key === "End") {
      e.preventDefault();
      goToSlide(totalSlides - 1, true);
      restartTimer();
    }
  });

  // Touch Swipe Gesture support
  card.addEventListener(
    "touchstart",
    (e) => {
      if (e.changedTouches.length === 1) {
        isTouching = true;
        stopTimer();
        touchStartX = e.changedTouches[0].screenX;
        touchStartY = e.changedTouches[0].screenY;
      }
    },
    { passive: true }
  );

  card.addEventListener(
    "touchend",
    (e) => {
      if (e.changedTouches.length === 1) {
        isTouching = false;
        const touchEndX = e.changedTouches[0].screenX;
        const touchEndY = e.changedTouches[0].screenY;
        const deltaX = touchEndX - touchStartX;
        const deltaY = touchEndY - touchStartY;

        // Minimum swipe threshold 45px and predominantly horizontal
        if (Math.abs(deltaX) > 45 && Math.abs(deltaX) > Math.abs(deltaY) * 1.5) {
          if (deltaX < 0) {
            // Swiped left -> next
            goToSlide(currentIndex + 1, true);
          } else {
            // Swiped right -> prev
            goToSlide(currentIndex - 1, true);
          }
        }
        startTimer();
      }
    },
    { passive: true }
  );

  card.addEventListener("touchcancel", () => {
    isTouching = false;
    startTimer();
  });

  // Listen for reduced motion preference changes
  if (reducedMotionMedia.addEventListener) {
    reducedMotionMedia.addEventListener("change", (e) => {
      prefersReducedMotion = e.matches;
      if (prefersReducedMotion) {
        setPlayPauseState(false);
      }
    });
  }

  // Initial display setup
  goToSlide(0, false);
  setPlayPauseState(!prefersReducedMotion);
});

