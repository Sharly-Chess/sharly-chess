{% with timer=screen.timer %}
{% with color_1_r=timer.color_1_rgb.0, color_1_g=timer.color_1_rgb.1, color_1_b=timer.color_1_rgb.2 %}
{% with color_2_r=timer.color_2_rgb.0, color_2_g=timer.color_2_rgb.1, color_2_b=timer.color_2_rgb.2 %}
{% with color_3_r=timer.color_3_rgb.0, color_3_g=timer.color_3_rgb.1, color_3_b=timer.color_3_rgb.2 %}
{% with delay_1=timer.delays.1, delay_2=timer.delays.2, delay_3=timer.delays.3 %}
var timer;
var timer_clock;
var timer_text;
function start_update_timer_interval() {
	timer = document.getElementById('timer');
	timer_clock = document.getElementById('timer-clock');
	timer_text = document.getElementById('timer-text');
	update_timer();
	setInterval('update_timer();', 1000);
}
function update_timer_values(clock_html, text_html, color) {
	if (timer_clock.innerHTML != clock_html) {
		timer_clock.innerHTML = clock_html;
	}
	if (timer.style.backgroundColor != color) {
		timer.style.backgroundColor = color;
	}
	if (timer_text.innerHTML != text_html) {
		timer_text.innerHTML = text_html;
	}
}
function two_digits(n) {
	return ('0' + n).slice(-2);
}
var format = function (str, col) {
    col = typeof col === 'object' ? col : Array.prototype.slice.call(arguments, 1);
    return str.replace(/\{\{|\}\}|\{(\w+)\}/g, function (m, n) {
        if (m == "{% raw %}{{{% endraw %}") { return "{"; }
        if (m == "{% raw %}}}}}{% endraw %}") { return "}"; }
        return col[n];
    });
};
String.prototype.format = function (col) {
    return format(this,col);
}
function weeks_days_hours_minutes_seconds_string(weeks, days, hours, minutes, seconds) {
	switch (weeks) {
	    case 0:
            switch (days) {
                case 0:
                    switch (hours) {
                        case 0:
                            switch (minutes) {
                                case 0:
                                    switch (seconds) {
                                        case 0:
                                        case 1:
                                            return "{{ _('{seconds} second') }}";
                                        default:
                                            return "{{ _('{seconds} seconds') }}";
                                    }
                                case 1:
                                    switch (minutes) {
                                        case 0: return "{{ _('{minutes} minute') }}";
                                        case 1: return "{{ _('{minutes} minute and {seconds} second') }}";
                                        default: return "{{ _('{minutes} minute and {seconds} seconds') }}";
                                    }
                                default:
                                    switch (minutes) {
                                        case 0: return "{{ _('{minutes} minutes') }}";
                                        case 1: return "{{ _('{minutes} minutes and {seconds} second') }}";
                                        default: return "{{ _('{minutes} minutes and {seconds} seconds') }}";
                                    }
                            }
                        case 1:
                            switch (minutes) {
                                case 0: return "{{ _('{hours} hour') }}";
                                case 1: return "{{ _('{hours} hour and {minutes} minute') }}";
                                default: return "{{ _('{hours} hour and {minutes} minutes') }}";
                            }
                        default:
                            switch (minutes) {
                                case 0: return "{{ _('{hours} hours') }}";
                                case 1: return "{{ _('{hours} hours and {minutes} minute') }}";
                                default: return "{{ _('{hours} hours and {minutes} minutes') }}";
                            }
                    }
                case 1:
                    switch (hours) {
                        case 0: return "{{ _('{days} day') }}";
                        case 1: return "{{ _('{days} day and {hours} hour') }}";
                        default: return "{{ _('{days} day and {hours} hours') }}";
                    }
                default:
                    switch (hours) {
                        case 0: return "{{ _('{days} days') }}";
                        case 1: return "{{ _('{days} days and {hours} hour') }}";
                        default: return "{{ _('{days} days and {hours} hours') }}";
                    }
            }
	    case 1:
            switch (days) {
                case 0: return "{{ _('{weeks} week') }}";
                case 1: return "{{ _('{weeks} week and {days} day') }}";
                default: return "{{ _('{weeks} week and {days} days') }}";
            }
	    default:
            switch (days) {
                case 0: return "{{ _('{weeks} weeks') }}";
                case 1: return "{{ _('{weeks} weeks and {days} day') }}";
                default: return "{{ _('{weeks} weeks and {days} days') }}";
            }
	}
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
	return weeks_days_hours_minutes_seconds_string(
	    weeks, days, hours, minutes, seconds
    ).replace(
        '{seconds}', seconds
    ).replace(
        '{minutes}', minutes
    ).replace(
        '{hours}', hours
    ).replace(
        '{days}', days
    ).replace(
        '{weeks}', weeks
    );
}
function update_timer() {
	now = new Date();
	time = Math.floor(now.getTime() / 1000);
	clock_html = two_digits(now.getHours())+':'+two_digits(now.getMinutes())+':'+two_digits(now.getSeconds());
{% for timer_hour in timer.timer_hours_sorted_by_order %}
  {% if not timer_hour.error %}
	if (time < {{ timer_hour.timestamp_1 }}) { // {{ timer_hour.datetime_str_1 }} color_1 {{ timer_hour.text_before }}
		color = 'rgb({{ color_1_r }},{{ color_1_g }},{{ color_1_b }})';
		dur = duration_string({{ timer_hour.timestamp }} - time);
		console.error('dur=' + dur)
		text_html = '{{ timer_hour.text_before }}'.replace('%s', dur);
		update_timer_values(clock_html, text_html, color);
		return;
	}
	if (time < {{ timer_hour.timestamp_2 }}) { // {{ timer_hour.datetime_str_2 }} color_1 -> color_2 {{ timer_hour.text_before }}
		color_r = Math.floor({{ color_1_r }} + (time - {{ timer_hour.timestamp_1 }})/({{ delay_1 * 60 }})*({{ color_2_r - color_1_r }}));
		color_g = Math.floor({{ color_1_g }} + (time - {{ timer_hour.timestamp_1 }})/({{ delay_1 * 60 }})*({{ color_2_g - color_1_g }}));
		color_b = Math.floor({{ color_1_b }} + (time - {{ timer_hour.timestamp_1 }})/({{ delay_1 * 60 }})*({{ color_2_b - color_1_b }}));
		color = 'rgb(' + color_r + ',' + color_g + ',' + color_b + ')';
		dur = duration_string({{ timer_hour.timestamp }} - time);
		text_html = '{{ timer_hour.text_before }}'.replace('%s', dur);
		update_timer_values(clock_html, text_html, color);
		return;
	}
	if (time < {{ timer_hour.timestamp_3 }}) { // {{ timer_hour.datetime_str_3 }} color_2 -> color_3 {{ timer_hour.text_before }}
		color_r = Math.floor({{ color_2_r }} + (time - {{ timer_hour.timestamp_2 }})/({{ delay_2 * 60 }})*({{ color_3_r - color_2_r }}));
		color_g = Math.floor({{ color_2_g }} + (time - {{ timer_hour.timestamp_2 }})/({{ delay_2 * 60 }})*({{ color_3_g - color_2_g }}));
		color_b = Math.floor({{ color_2_b }} + (time - {{ timer_hour.timestamp_2 }})/({{ delay_2 * 60 }})*({{ color_3_b - color_2_b }}));
		color = 'rgb(' + color_r + ',' + color_g + ',' + color_b + ')';
		dur = duration_string({{ timer_hour.timestamp }} - time);
		text_html = '{{ timer_hour.text_before }}'.replace('%s', dur);
		update_timer_values(clock_html, text_html, color);
		return;
	}
	{% if not timer_hour.last_valid %}
	if (time < {{ timer_hour.timestamp_next }}) { // {{ timer_hour.datetime_str_next }} color_3 {{ timer_hour.text_after }}
	{% endif %}
		color = 'rgb({{ color_3_r }},{{ color_3_g }},{{ color_3_b }})';
		dur = duration_string(time - {{ timer_hour.timestamp }});
		text_html = '{{ timer_hour.text_after }}'.replace('%s', dur);
		update_timer_values(clock_html, text_html, color);
		return;
	{% if not timer_hour.last_valid %}
	}
	{% endif %}
  {% endif %}
{% endfor %}
}
$(document).ready(function(){
    start_update_timer_interval();
});
{% endwith %}
{% endwith %}
{% endwith %}
{% endwith %}
{% endwith %}
