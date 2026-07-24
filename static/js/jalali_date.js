/**
 * JalaliDate - Persian Calendar Utility
 * 
 * A lightweight JavaScript library for converting between Jalali (Persian) 
 * and Gregorian calendars.
 * 
 * @version 1.0.0
 * @author Your Team
 */

class JalaliDate {
    /**
     * Create a JalaliDate instance
     * @param {number} jy - Jalali year
     * @param {number} jm - Jalali month (1-12)
     * @param {number} jd - Jalali day
     */
    constructor(jy, jm, jd) {
        if (arguments.length === 0) {
            const now = new Date();
            const [y, m, d] = JalaliDate.gregorianToJalali(
                now.getFullYear(), 
                now.getMonth() + 1, 
                now.getDate()
            );
            this.jy = y;
            this.jm = m;
            this.jd = d;
        } else {
            this.jy = jy;
            this.jm = jm;
            this.jd = jd;
        }
    }

    /**
     * Get today's date in Jalali calendar
     * @returns {JalaliDate}
     */
    static today() {
        return new JalaliDate();
    }

    /**
     * Convert Gregorian date to Jalali
     * @param {number} gy - Gregorian year
     * @param {number} gm - Gregorian month (1-12)
     * @param {number} gd - Gregorian day
     * @returns {Array<number>} [jy, jm, jd]
     */
    static gregorianToJalali(gy, gm, gd) {
        const g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334];
        let jy, jm, jd;
        
        if (gy > 1600) {
            jy = 979;
            gy -= 1600;
        } else {
            jy = 0;
            gy -= 621;
        }
        
        const gy2 = (gm > 2) ? (gy + 1) : gy;
        let days = (365 * gy) + Math.floor((gy2 + 3) / 4) - Math.floor((gy2 + 99) / 100) + 
                   Math.floor((gy2 + 399) / 400) - 80 + gd + g_d_m[gm - 1];
        
        jy += 33 * Math.floor(days / 12053);
        days %= 12053;
        
        jy += 4 * Math.floor(days / 1461);
        days %= 1461;
        
        if (days > 365) {
            jy += Math.floor((days - 1) / 365);
            days = (days - 1) % 365;
        }
        
        if (days < 186) {
            jm = 1 + Math.floor(days / 31);
            jd = 1 + (days % 31);
        } else {
            jm = 7 + Math.floor((days - 186) / 30);
            jd = 1 + ((days - 186) % 30);
        }
        
        return [jy, jm, jd];
    }

    /**
     * Convert Jalali date to Gregorian
     * @param {number} jy - Jalali year
     * @param {number} jm - Jalali month (1-12)
     * @param {number} jd - Jalali day
     * @returns {Array<number>} [gy, gm, gd]
     */
    static jalaliToGregorian(jy, jm, jd) {
        let gy, gm, gd;
        
        if (jy > 979) {
            gy = 1600;
            jy -= 979;
        } else {
            gy = 621;
        }
        
        let days = (365 * jy) + (Math.floor(jy / 33) * 8) + 
                   Math.floor(((jy % 33) + 3) / 4) + 78 + jd;
        
        if (jm < 7) {
            days += (jm - 1) * 31;
        } else {
            days += ((jm - 7) * 30) + 186;
        }
        
        gy += 400 * Math.floor(days / 146097);
        days %= 146097;
        
        let leap = true;
        if (days >= 36525) {
            days--;
            gy += 100 * Math.floor(days / 36524);
            days %= 36524;
            
            if (days >= 365) {
                days++;
            } else {
                leap = false;
            }
        }
        
        gy += 4 * Math.floor(days / 1461);
        days %= 1461;
        
        if (days >= 366) {
            leap = false;
            days--;
            gy += Math.floor(days / 365);
            days = (days % 365) + 1;
        }
        
        const sal_a = [0, 31, (leap ? 29 : 28), 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
        
        gm = 0;
        while (gm < 13 && days > sal_a[gm]) {
            days -= sal_a[gm];
            gm++;
        }
        
        gd = days;
        
        return [gy, gm, gd];
    }

    /**
     * Convert this Jalali date to Gregorian Date object
     * @returns {Date}
     */
    toGregorian() {
        const [gy, gm, gd] = JalaliDate.jalaliToGregorian(this.jy, this.jm, this.jd);
        return new Date(gy, gm - 1, gd);
    }

    /**
     * Format as string YYYY-MM-DD
     * @returns {string}
     */
    toString() {
        return `${this.jy}-${String(this.jm).padStart(2, '0')}-${String(this.jd).padStart(2, '0')}`;
    }

    /**
     * Get Persian month name
     * @returns {string}
     */
    getMonthName() {
        const months = [
            'فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور',
            'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند'
        ];
        return months[this.jm - 1];
    }

    /**
     * Get Persian day name
     * @returns {string}
     */
    getDayName() {
        const days = ['یکشنبه', 'دوشنبه', 'سه‌شنبه', 'چهارشنبه', 'پنج‌شنبه', 'جمعه', 'شنبه'];
        const gDate = this.toGregorian();
        return days[gDate.getDay()];
    }

    /**
     * Get short Persian day name
     * @returns {string}
     */
    getShortDayName() {
        const days = ['یکشنبه', 'دوشنبه', 'سه‌شنبه', 'چهارشنبه', 'پنج‌شنبه', 'جمعه', 'شنبه'];
        const gDate = this.toGregorian();
        return days[gDate.getDay()];
    }

    /**
     * Add days to this date
     * @param {number} days - Number of days to add
     * @returns {JalaliDate}
     */
    addDays(days) {
        const gDate = this.toGregorian();
        gDate.setDate(gDate.getDate() + days);
        const [jy, jm, jd] = JalaliDate.gregorianToJalali(
            gDate.getFullYear(), 
            gDate.getMonth() + 1, 
            gDate.getDate()
        );
        return new JalaliDate(jy, jm, jd);
    }

    /**
     * Get number of days in current month
     * @returns {number}
     */
    daysInMonth() {
        if (this.jm <= 6) return 31;
        if (this.jm <= 11) return 30;
        return 29; // Simplified, doesn't account for leap years
    }
}

// Export for use in modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = JalaliDate;
}
