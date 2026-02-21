document.addEventListener('alpine:init', () => {
    Alpine.data('datasetCard', () => ({
        show: false,
        toggle() { this.show = !this.show },
        key: ALPINE_KEY,
        login: ALPINE_LOGIN
    }))
})