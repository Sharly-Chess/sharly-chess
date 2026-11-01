{% with color_1_r=timer.color_1_rgb.0, color_1_g=timer.color_1_rgb.1, color_1_b=timer.color_1_rgb.2 %}
{% with color_2_r=timer.color_2_rgb.0, color_2_g=timer.color_2_rgb.1, color_2_b=timer.color_2_rgb.2 %}
{% with color_3_r=timer.color_3_rgb.0, color_3_g=timer.color_3_rgb.1, color_3_b=timer.color_3_rgb.2 %}
{% with delay_1=timer.delays.1, delay_2=timer.delays.2, delay_3=timer.delays.3 %}

var timer;
var timerColor;
var polyglot = new Polyglot({
    locale: '{{ locale }}',
    phrases: {
        'seconds': '{{ _('<smart_count> second |||| <smart_count> seconds') }}',
        'minutes': '{{ _('<smart_count> minute |||| <smart_count> minutes') }}',
        'hours': '{{ _('<smart_count> hour |||| <smart_count> hours') }}',
        'days': '{{ _('<smart_count> day |||| <smart_count> days') }}',
        'weeks': '{{ _('<smart_count> week |||| <smart_count> weeks') }}',
        'countdown': '{{ _('<first> <second>') }}',
    },
    interpolation: {
        prefix: '<',
        suffix: '>',
    },
});

// Black or white, whichever reads better on the timer colour.
function timer_ink(color) {
    const channels = color.match(/\d+/g).slice(0, 3).map(function(value) {
        value /= 255;
        return value <= 0.03928 ? value / 12.92 : Math.pow((value + 0.055) / 1.055, 2.4);
    });
    const luminance = 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
    return 1.05 / (luminance + 0.05) >= (luminance + 0.05) / 0.05 ? '#ffffff' : '#101418';
}

// The first title of the screen sits beside the timer, keeps clear of it and is
// at least as tall; the timer is centred on that title line.
function update_timer_width() {
    const wrapper = document.getElementById('timer-wrapper');
    const shown = wrapper && !wrapper.classList.contains('d-none');
    const root = document.documentElement;
    root.style.setProperty('--timer-width', (shown ? wrapper.offsetWidth : 0) + 'px');
    if (!shown) {
        root.style.setProperty('--timer-height', '0px');
        return;
    }
    const pill = document.getElementById('timer');
    const clock = document.getElementById('timer-clock');
    root.style.setProperty('--timer-height', Math.max(pill.offsetHeight, clock.offsetHeight) + 'px');
    const title = document.querySelector(
        '#user-screen-content .screen > .set-title:first-child, '
        + '#user-screen-content .screen > :first-child > .set-title:first-child'
    );
    if (title && getComputedStyle(wrapper).position === 'absolute') {
        const titleBox = title.getBoundingClientRect();
        const top = titleBox.top - wrapper.offsetParent.getBoundingClientRect().top;
        wrapper.style.top = top + 'px';
        wrapper.style.height = titleBox.height - parseFloat(getComputedStyle(title).borderBottomWidth) + 'px';
    } else {
        wrapper.style.top = '';
        wrapper.style.height = '';
    }
}

function update_timer_values(clock_html, text_html, color) {
	$('#timer-wrapper').removeClass('d-none');
    $('#timer-clock').text(clock_html);
    $('#timer-text').text(text_html);
    timerColor = color;
    $('#timer').css({'background-color': color, 'color': timer_ink(color)});
    update_timer_width();
}

function two_digits(n) {
	return ('0' + n).slice(-2);
}
function duration_string(dur) {
	seconds = dur % 60;
	dur = (dur - seconds)/60;
	minutes = dur % 60;
	dur = (dur - minutes)/60;
	hours = dur % 24;
	dur = (dur - hours)/24;
	days = dur % 7;
	weeks = (dur - days)/7;

    if (weeks > 0) {
        first = polyglot.t('weeks', weeks);
        second = days > 0 ? polyglot.t('days', days) : undefined;
    } else if (days > 0) {
        first = polyglot.t('days', days);
        second = hours > 0 ? polyglot.t('hours', hours) : undefined;
    } else if (hours > 0) {
        first = polyglot.t('hours', hours);
        second = minutes > 0 ? polyglot.t('minutes', minutes) : undefined;
    } else if (minutes > 0) {
        first = polyglot.t('minutes', minutes);
        second = undefined;
    } else {
        first = polyglot.t('seconds', seconds);
        second = undefined;
    }

    if (second) {
        return polyglot.t('countdown', {
            first: first,
            second: second,
        });
    }

    return first;
}
function update_timer(local_delay) {
	local_date = new Date();
	local_time = Math.floor(local_date.getTime() / 1000);
	server_time = Math.floor(local_date.getTime() / 1000) + local_delay;
    server_date = new Date(server_time * 1000)
	clock_html = two_digits(server_date.getHours())+':'+two_digits(server_date.getMinutes());
{% for timer_hour in timer.timer_hours %}
	if (server_time < {{ timer_hour.timestamp_1 }}) {
		color = 'rgb({{ color_1_r }}, {{ color_1_g }}, {{ color_1_b }})';
		dur = duration_string({{ timer_hour.timestamp }} - server_time);
		text_html = '{{ timer_hour.text_before | replace ("'", "\\'") | safe }}'.replace('%s', dur);
		update_timer_values(clock_html, text_html, color);
		return;
	}
	if (server_time < {{ timer_hour.timestamp_2 }}) {
		color_r = Math.floor({{ color_1_r }} + (server_time - {{ timer_hour.timestamp_1 }})/({{ delay_1 * 60 }})*({{ color_2_r - color_1_r }}));
		color_g = Math.floor({{ color_1_g }} + (server_time - {{ timer_hour.timestamp_1 }})/({{ delay_1 * 60 }})*({{ color_2_g - color_1_g }}));
		color_b = Math.floor({{ color_1_b }} + (server_time - {{ timer_hour.timestamp_1 }})/({{ delay_1 * 60 }})*({{ color_2_b - color_1_b }}));
		color = 'rgb(' + color_r + ', ' + color_g + ', ' + color_b + ')';
		dur = duration_string({{ timer_hour.timestamp }} - server_time);
		text_html = '{{ timer_hour.text_before | replace ("'", "\\'") | safe }}'.replace('%s', dur);
		update_timer_values(clock_html, text_html, color);
		return;
	}
	if (server_time < {{ timer_hour.timestamp_3 }}) {
		color_r = Math.floor({{ color_2_r }} + (server_time - {{ timer_hour.timestamp_2 }})/({{ delay_2 * 60 }})*({{ color_3_r - color_2_r }}));
		color_g = Math.floor({{ color_2_g }} + (server_time - {{ timer_hour.timestamp_2 }})/({{ delay_2 * 60 }})*({{ color_3_g - color_2_g }}));
		color_b = Math.floor({{ color_2_b }} + (server_time - {{ timer_hour.timestamp_2 }})/({{ delay_2 * 60 }})*({{ color_3_b - color_2_b }}));
		color = 'rgb(' + color_r + ', ' + color_g + ', ' + color_b + ')';
		dur = duration_string({{ timer_hour.timestamp }} - server_time);
		text_html = '{{ timer_hour.text_before | replace ("'", "\\'") | safe }}'.replace('%s', dur);
		update_timer_values(clock_html, text_html, color);
		return;
	}
	if (server_time < {{ timer_hour.timestamp_next }}) {
		color = 'rgb({{ color_3_r }}, {{ color_3_g }}, {{ color_3_b }})';
		dur = duration_string(server_time - {{ timer_hour.timestamp }});
		text_html = '{{ timer_hour.text_after | replace ("'", "\\'") | safe }}'.replace('%s', dur);
		update_timer_values(clock_html, text_html, color);
		return;
	}
{% endfor %}
    $('#timer-wrapper').addClass('d-none');
    update_timer_width();
}

$(document).ready(function(){
	now = new Date();
	local_time = Math.floor(now.getTime() / 1000);
    server_time = Math.floor({{ now }});
    local_delay = server_time - local_time;
    if (!timer) timer = setInterval('update_timer(' + local_delay + ');', 1000);
    update_timer(local_delay);
});

{% endwith %}
{% endwith %}
{% endwith %}
{% endwith %}
