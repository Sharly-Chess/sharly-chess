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
function duration(duration) {
	seconds = duration % 60;
	duration = (duration - seconds)/60;
	minutes = duration % 60;
	duration = (duration - minutes)/60;
	hours = duration % 24;
	duration = (duration - hours)/24;
	days = duration % 7;
	weeks = (duration - days)/7;
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
                                            return "{{ _('{0} second') }}".format(seconds)
                                        default:
                                            return "{{ _('{0} seconds') }}".format(seconds)
                                    }
                                case 1:
                                    switch (minutes) {
                                        case 0: return "{{ _('{0} minute') }}".format(minutes)
                                        case 1: return "{{ _('{0} minute and {1} second') }}".format(minutes, seconds)
                                        default: return "{{ _('{0} minute and {1} seconds') }}".format(minutes, seconds)
                                    }
                                default:
                                    switch (minutes) {
                                        case 0: return "{{ _('{0} minutes') }}".format(minutes)
                                        case 1: return "{{ _('{0} minutes and {1} second') }}".format(minutes, seconds)
                                        default: return "{{ _('{0} minutes and {1} seconds') }}".format(minutes, seconds)
                                    }
                            }
                        case 1:
                            switch (minutes) {
                                case 0: return "{{ _('{0} hour') }}".format(hours)
                                case 1: return "{{ _('{0} hour and {1} minute') }}".format(hours, minutes)
                                default: return "{{ _('{0} hour and {1} minutes') }}".format(hours, minutes)
                            }
                        default:
                            switch (minutes) {
                                case 0: return "{{ _('{0} hours') }}".format(hours)
                                case 1: return "{{ _('{0} hours and {1} minute') }}".format(hours, minutes)
                                default: return "{{ _('{0} hours and {1} minutes') }}".format(hours, minutes)
                            }
                    }
                case 1:
                    switch (hours) {
                        case 0: return "{{ _('{0} day') }}".format(days)
                        case 1: return "{{ _('{0} day and {1} hour') }}".format(days, hours)
                        default: return "{{ _('{0} day and {1} hours') }}".format(days, hours)
                    }
                default:
                    switch (hours) {
                        case 0: return "{{ _('{0} days') }}".format(days)
                        case 1: return "{{ _('{0} days and {1} hour') }}".format(days, hours)
                        default: return "{{ _('{0} days and {1} hours') }}".format(days, hours)
                    }
            }
	    case 1:
            switch (days) {
                case 0: return "{{ _('{0} week') }}".format(weeks)
                case 1: return "{{ _('{0} week and {1} day') }}".format(weeks, days)
                default: return "{{ _('{0} week and {1} days') }}".format(weeks, days)
            }
	    default:
            switch (days) {
                case 0: return "{{ _('{0} weeks') }}".format(weeks)
                case 1: return "{{ _('{0} weeks and {1} day') }}".format(weeks, days)
                default: return "{{ _('{0} weeks and {1} days') }}".format(weeks, days)
            }
	}
}
function update_timer() {
	now = new Date();
	time = Math.floor(now.getTime() / 1000);
	clock_html = two_digits(now.getHours())+':'+two_digits(now.getMinutes())+':'+two_digits(now.getSeconds());
{% for timer_hour in timer.timer_hours_sorted_by_order %}
  {% if not timer_hour.error %}
	if (time < {{ timer_hour.timestamp_1 }}) { // {{ timer_hour.datetime_str_1 }} color_1 {{ timer_hour.text_before }}
		color = 'rgb({{ color_1_r }},{{ color_1_g }},{{ color_1_b }})';
		dur = duration({{ timer_hour.timestamp }} - time);
		text_html = '{{ timer_hour.text_before }}'.replace('%s', dur);
		update_timer_values(clock_html, text_html, color);
		return;
	}
	if (time < {{ timer_hour.timestamp_2 }}) { // {{ timer_hour.datetime_str_2 }} color_1 -> color_2 {{ timer_hour.text_before }}
		color_r = Math.floor({{ color_1_r }} + (time - {{ timer_hour.timestamp_1 }})/({{ delay_1 * 60 }})*({{ color_2_r - color_1_r }}));
		color_g = Math.floor({{ color_1_g }} + (time - {{ timer_hour.timestamp_1 }})/({{ delay_1 * 60 }})*({{ color_2_g - color_1_g }}));
		color_b = Math.floor({{ color_1_b }} + (time - {{ timer_hour.timestamp_1 }})/({{ delay_1 * 60 }})*({{ color_2_b - color_1_b }}));
		color = 'rgb(' + color_r + ',' + color_g + ',' + color_b + ')';
		dur = duration({{ timer_hour.timestamp }} - time);
		text_html = '{{ timer_hour.text_before }}'.replace('%s', dur);
		update_timer_values(clock_html, text_html, color);
		return;
	}
	if (time < {{ timer_hour.timestamp_3 }}) { // {{ timer_hour.datetime_str_3 }} color_2 -> color_3 {{ timer_hour.text_before }}
		color_r = Math.floor({{ color_2_r }} + (time - {{ timer_hour.timestamp_2 }})/({{ delay_2 * 60 }})*({{ color_3_r - color_2_r }}));
		color_g = Math.floor({{ color_2_g }} + (time - {{ timer_hour.timestamp_2 }})/({{ delay_2 * 60 }})*({{ color_3_g - color_2_g }}));
		color_b = Math.floor({{ color_2_b }} + (time - {{ timer_hour.timestamp_2 }})/({{ delay_2 * 60 }})*({{ color_3_b - color_2_b }}));
		color = 'rgb(' + color_r + ',' + color_g + ',' + color_b + ')';
		dur = duration({{ timer_hour.timestamp }} - time);
		text_html = '{{ timer_hour.text_before }}'.replace('%s', dur);
		update_timer_values(clock_html, text_html, color);
		return;
	}
	{% if not timer_hour.last_valid %}
	if (time < {{ timer_hour.timestamp_next }}) { // {{ timer_hour.datetime_str_next }} color_3 {{ timer_hour.text_after }}
	{% endif %}
		color = 'rgb({{ color_3_r }},{{ color_3_g }},{{ color_3_b }})';
		dur = duration(time - {{ timer_hour.timestamp }});
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
