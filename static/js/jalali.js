/**
 * JalaliDate - Persian (Jalali) Calendar Implementation
 * Non-module version for use with regular <script> tags
 */

(function (window) {
  "use strict";

  /**
   * JalaliDate class for Persian calendar
   */
  function JalaliDate(jy, jm, jd) {
    if (arguments.length === 0) {
      // No args - create from current date
      const now = new Date();
      const gResult = gregorianToJalali(
        now.getFullYear(),
        now.getMonth() + 1,
        now.getDate(),
      );
      this.jy = gResult[0];
      this.jm = gResult[1];
      this.jd = gResult[2];
    } else if (arguments.length === 3) {
      // Three args - jy, jm, jd
      this.jy = jy;
      this.jm = jm;
      this.jd = jd;
    } else {
      throw new Error("Invalid arguments for JalaliDate");
    }
  }

  /**
   * Static method to get today's Jalali date
   */
  JalaliDate.today = function () {
    return new JalaliDate();
  };

  /**
   * Convert Gregorian to Jalali
   */
  function gregorianToJalali(gy, gm, gd) {
    const g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334];

    let jy, jm, jd;

    if (gy > 1600) {
      jy = 979;
      gy -= 1600;
    } else {
      jy = 0;
      gy -= 621;
    }

    let gy2 = gm > 2 ? gy + 1 : gy;
    let days =
      365 * gy +
      Math.floor((gy2 + 3) / 4) -
      Math.floor((gy2 + 99) / 100) +
      Math.floor((gy2 + 399) / 400) -
      80 +
      gd +
      g_d_m[gm - 1];

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
   * Convert Jalali to Gregorian
   */
  function jalaliToGregorian(jy, jm, jd) {
    let gy, gm, gd;

    if (jy > 979) {
      gy = 1600;
      jy -= 979;
    } else {
      gy = 621;
    }

    let days =
      365 * jy +
      Math.floor(jy / 33) * 8 +
      Math.floor(((jy % 33) + 3) / 4) +
      78 +
      jd;

    if (jm < 7) {
      days += (jm - 1) * 31;
    } else {
      days += (jm - 7) * 30 + 186;
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

    const sal_a = [
      0,
      31,
      leap ? 29 : 28,
      31,
      30,
      31,
      30,
      31,
      31,
      30,
      31,
      30,
      31,
    ];

    gm = 0;
    while (gm < 13 && days > sal_a[gm]) {
      days -= sal_a[gm];
      gm++;
    }

    gd = days;

    return [gy, gm, gd];
  }

  /**
   * Instance methods
   */
  JalaliDate.prototype.toGregorian = function () {
    const result = jalaliToGregorian(this.jy, this.jm, this.jd);
    return new Date(result[0], result[1] - 1, result[2]);
  };

  JalaliDate.prototype.toString = function () {
    return (
      this.jy +
      "-" +
      String(this.jm).padStart(2, "0") +
      "-" +
      String(this.jd).padStart(2, "0")
    );
  };

  JalaliDate.prototype.format = function (pattern) {
    pattern = pattern || "YYYY-MM-DD";
    return pattern
      .replace("YYYY", this.jy)
      .replace("MM", String(this.jm).padStart(2, "0"))
      .replace("DD", String(this.jd).padStart(2, "0"));
  };

  JalaliDate.prototype.getMonthName = function () {
    const months = [
      "فروردین",
      "اردیبهشت",
      "خرداد",
      "تیر",
      "مرداد",
      "شهریور",
      "مهر",
      "آبان",
      "آذر",
      "دی",
      "بهمن",
      "اسفند",
    ];
    return months[this.jm - 1];
  };

  JalaliDate.prototype.getDayName = function () {
    const days = [
      "شنبه",
      "یکشنبه",
      "دوشنبه",
      "سه‌شنبه",
      "چهارشنبه",
      "پنج‌شنبه",
      "جمعه",
    ];
    const gDate = this.toGregorian();
    return days[gDate.getDay()];
  };

  JalaliDate.prototype.getShortDayName = function () {
    const days = ["ش", "ی", "د", "س", "چ", "پ", "ج"];
    const gDate = this.toGregorian();
    return days[gDate.getDay()];
  };

  JalaliDate.prototype.addDays = function (days) {
    const gDate = this.toGregorian();
    gDate.setDate(gDate.getDate() + days);
    const result = gregorianToJalali(
      gDate.getFullYear(),
      gDate.getMonth() + 1,
      gDate.getDate(),
    );
    return new JalaliDate(result[0], result[1], result[2]);
  };

  JalaliDate.prototype.addMonths = function (months) {
    let jy = this.jy;
    let jm = this.jm + months;
    let jd = this.jd;

    while (jm > 12) {
      jm -= 12;
      jy++;
    }
    while (jm < 1) {
      jm += 12;
      jy--;
    }

    // Adjust day if it exceeds month length
    const maxDay = jm <= 6 ? 31 : jm <= 11 ? 30 : 29;
    if (jd > maxDay) {
      jd = maxDay;
    }

    return new JalaliDate(jy, jm, jd);
  };

  JalaliDate.prototype.addYears = function (years) {
    return new JalaliDate(this.jy + years, this.jm, this.jd);
  };

  JalaliDate.prototype.isBefore = function (other) {
    const thisG = this.toGregorian();
    const otherG = other.toGregorian();
    return thisG < otherG;
  };

  JalaliDate.prototype.isAfter = function (other) {
    const thisG = this.toGregorian();
    const otherG = other.toGregorian();
    return thisG > otherG;
  };

  JalaliDate.prototype.isSame = function (other) {
    return this.jy === other.jy && this.jm === other.jm && this.jd === other.jd;
  };

  // Static utility functions
  JalaliDate.gregorianToJalali = gregorianToJalali;
  JalaliDate.jalaliToGregorian = jalaliToGregorian;

  // Export to window (global)
  window.JalaliDate = JalaliDate;
})(window);
