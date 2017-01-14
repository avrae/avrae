

function parsesize (size) {
	if (size == "T") size = "Tiny";
	if (size == "S") size = "Small";
	if (size == "M") size = "Medium";
	if (size == "L") size = "Large";
	if (size == "H") size = "Huge";
	if (size == "G") size = "Gargantuan";
	return size;
}

function tagcontent (curitem, tag, multi=false) {
	if (!curitem.getElementsByTagName(tag).length) return false;
	return curitem.getElementsByTagName(tag)[0].childNodes[0].nodeValue;
}

window.onload = loadraces;

function loadraces() {
	tabledefault = $("#stats").html();

	var racelist = racedata.compendium.race;

	for (var i = 0; i < racelist.length; i++) {
		var currace = racelist[i];
		var name = currace.name;
		if (!racelist[i].ability) racelist[i].ability = "";
		$("ul.races").append("<li id='"+i+"' data-link='"+encodeURI(name)+"'><span class='name'>"+name+"</span> <span class='ability'>"+racelist[i].ability.replace(/(?:\s)(\d)/g, " +$1")+"</span> <span class='size'>"+parsesize(racelist[i].size)+"</span></li>");
	}

	var options = {
		valueNames: ['name', 'ability', 'size'],
		listClass: "races"
	}

	var raceslist = new List("listcontainer", options);
	raceslist.sort ("name")

	$("ul.list li").mousedown(function(e) {
		if (e.which === 2) {
			console.log("#"+$(this).attr("data-link"))
			window.open("#"+$(this).attr("data-link"), "_blank").focus();
			e.preventDefault();
			e.stopPropagation();
			return;
		}
	});

	$("ul.list li").click(function(e) {
		userace($(this).attr("id"));
		document.title = decodeURI($(this).attr("data-link")) + " - 5etools Races";
		window.location = "#"+$(this).attr("data-link");
	});

	if (window.location.hash.length) {
		$("ul.list li[data-link='"+window.location.hash.split("#")[1]+"']:eq(0)").click();
	} else $("ul.list li:eq(0)").click();
}

function userace (id) {
	$("#stats").html(tabledefault);
	$("#stats td").show();

	var racelist = racedata.compendium.race;
	var currace = racelist[id];

	var name = currace.name;
	$("th#name").html(name);

	var size = parsesize (currace.size);
	$("td#size span").html(size);
	if (size === "") $("td#size").hide();

	var ability = currace.ability.replace(/(?:\s)(\d)/g, " +$1");
	$("td#ability span").html(ability);

	var speed = currace.speed;
	$("td#speed span").html(speed+ "ft. ");
	if (speed === "") $("td#speed").hide();

	var traitlist = currace.trait;
	$("tr.trait").remove();
	for (var n = traitlist.length-1; n >= 0; n--) {
		var traitname = traitlist[n].name+".";
		if (traitname.indexOf("Variant Feature") !== -1) {
			traitname = traitname + "</span><p></p><span>"
		}
		texthtml = "<span class='name'>"+traitname+"</span> <p>"+traitlist[n].text.join("</p><p></p><p>")+"</p>"

		$("tr#traits").after("<tr class='trait'><td colspan='6' class='trait"+n+"'>"+texthtml+"</td></tr>");
	}
	return;
};
