// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

require(["jquery", "bootstrap", "moment", "jhapi", "utils"], function ($, bs, moment, JHAPI, utils) {
    "use strict";
    
    var base_url = window.jhdata.base_url;
    var prefix = window.jhdata.prefix;
    
    var api = new JHAPI(base_url);
    
    function get_row (element) {
        while (!element.hasClass("user-row")) {
            element = element.parent();
        }
        return element;
    }
    
    function resort (col, order) {
        var query = window.location.search.slice(1).split('&');
        // if col already present in args, remove it
        var i = 0;
        while (i < query.length) {
            if (query[i] === 'sort=' + col) {
                query.splice(i,1);
                if (query[i] && query[i].substr(0, 6) === 'order=') {
                    query.splice(i,1);
                }
            } else {
                i += 1;
            }
        }
        // add new order to the front
        if (order) {
            query.unshift('order=' + order);
        }
        query.unshift('sort=' + col);
        // reload page with new order
        window.location = window.location.pathname + '?' + query.join('&');
    }
    
    $("th").map(function (i, th) {
        th = $(th);
        var col = th.data('sort');
        if (!col || col.length === 0) {
            return;
        }
        var order = th.find('i').hasClass('fa-sort-desc') ? 'asc':'desc';
        th.find('a').click(
            function () {
                resort(col, order);
            }
        );
    });
    
    $(".time-col").map(function (i, el) {
        // convert ISO datestamps to nice momentjs ones
        el = $(el);
        el.text(moment(new Date(el.text())).fromNow());
    });
    
    $(".stop-server").click(function () {
        var el = $(this);
        var row = get_row(el);
        var user = row.data('user');
        el.text("stopping...");
        api.stop_server(user, {
            success: function () {
                el.text('stop server').addClass('hidden');
                row.find('.access-server').addClass('hidden');
                row.find('.start-server').removeClass('hidden');
            }
        });
    });
    
    $(".access-server").click(function () {
        var el = $(this);
        var row = get_row(el);
        var user = row.data('user');
        var w = window.open(utils.url_path_join(prefix, 'user', user));
    });
    
    $(".start-server").click(function () {
        var el = $(this);
        var row = get_row(el);
        var user = row.data('user');
        el.text("starting...");
        api.start_server(user, {
            success: function () {
                el.text('start server').addClass('hidden');
                row.find('.stop-server').removeClass('hidden');
                row.find('.access-server').removeClass('hidden');
            }
        });
    });
    
    $(".edit-user").click(function () {
        var el = $(this);
        var row = get_row(el);
        var user = row.data('user');
        var admin = row.data('admin');
        var dialog = $("#edit-user-dialog");
        dialog.find(".data_dir").prop("hidden", false);
        dialog.find(".home").prop("hidden", false);
        dialog.find(".shell").prop("hidden", false);
        dialog.data('user', user);
        dialog.find(".username-input").val(user);
        dialog.find("#edit-user-label").html('修改用户');
        dialog.find(".btn.btn-primary.save-button").html('确定');
        dialog.find(".btn.btn-default").html('取消');
        dialog.find(".admin-checkbox").attr("checked", admin==='True');
        dialog.find("#home").val('');
        dialog.find("#shell").val('');
        dialog.find("#data_dir").val('');
        //dialog.modal({backdrop: 'static'});
        api.edit_user_before(user, {
            async: false,
            success: function(data) {
                var obj = eval(data);
                var name  = obj.name;
                var shell = obj.shell;
                var home   = obj.home;
                var data  = obj.dir;
                console.log(name, shell, home, data);
                if (name != user)
                 {
                    alert('user not fit.');
                    return
                 }
                var dialog = $("#edit-user-dialog");
                dialog.find("#home").val(home);
                dialog.find("#shell").val(shell);
                dialog.find("#data_dir").val(data);
                dialog.modal();
            },
            error: function(jqXHR, status, error) {
//                var dialog = $("#edit-user-dialog");
//                dialog.prop("aria-hidden", true);
//                var url = document.URL;
//                console.log(url);
                //$("#edit-user-dialog").find(".modal-backdrop").remove();
                //$(".model-open").find(".modal-backdrop").remove();
//                $("#edit-user-dialog").load(url + ' #edit-user-dialog');
                utils.ajax_error_dialog(jqXHR, status, error);
            }
        });
        //dialog.modal();
    });
    
    $("#edit-user-dialog").find(".save-button").click(function () {
        var dialog = $("#edit-user-dialog");
        var user   = dialog.data('user');
        var name   = dialog.find(".username-input").val();
        var admin  = dialog.find(".admin-checkbox").prop("checked");

        var home  = dialog.find("#home").val();
        var shell = dialog.find("#shell").val();
        var data  = dialog.find("#data_dir").val();
        api.edit_user(user, {
            admin: admin,
            name:  name,
            home:  home,
            shell: shell,
            data:  data,
        }, {
            success: function () {
                window.location.reload();
            }
        });
    });
    
    
    $(".delete-user").click(function () {
        var el = $(this);
        var row = get_row(el);
        var user = row.data('user');
        var dialog = $("#delete-user-dialog");
        dialog.find('#delete-user-label').html('删除用户');
        dialog.find(".delete-button").html('确定');
        dialog.find(".btn-default").html('取消');
        dialog.find(".delete-username").text(user);
        dialog.modal();
    });

    $("#delete-user-dialog").find(".delete-button").click(function () {
        var dialog = $("#delete-user-dialog");
        var username = dialog.find(".delete-username").text();
        console.log("deleting", username);
        api.delete_user(username, {
            success: function () {
                window.location.reload();
            }
        });
    });
    
    $("#add-users").click(function () {
        var dialog = $("#add-users-dialog");
        dialog.find(".data_dir").prop("hidden", true)
        dialog.find(".home").prop("hidden", true)
        dialog.find(".shell").prop("hidden", true)
        dialog.find(".username-input").val('');
        dialog.find("#add-users-label").html('添加用户');
        dialog.find(".save-button").html('确定');
        dialog.find(".btn-default").html('取消');
        dialog.find(".admin-checkbox").prop("checked", false);
        dialog.modal();
    });

    $("#add-users-dialog").find(".save-button").click(function () {
        var dialog = $("#add-users-dialog");
        var lines = dialog.find(".username-input").val().split('\n');
        var admin = dialog.find(".admin-checkbox").prop("checked");
        var usernames = [];
        lines.map(function (line) {
            var username = line.trim();
            if (username.length) {
                usernames.push(username);
            }
        });
        
        api.add_users(usernames, {admin: admin}, {
            success: function () {
                window.location.reload();
            }
        });
    });

    $("#stop-all-servers").click(function () {
        $("#stop-all-servers-dialog").find("#stop-all-servers-label").html('停止所有服务');
        $("#stop-all-servers-dialog").find(".stop-all-button").html('确定');
        $("#stop-all-servers-dialog").find(".btn-default").html('取消');
        $("#stop-all-servers-dialog").modal();
    });

    $("#stop-all-servers-dialog").find(".stop-all-button").click(function () {
        // stop all clicks all the active stop buttons
        $('.stop-server').not('.hidden').click();
    });

    $("#shutdown-hub").click(function () {
        var dialog = $("#shutdown-hub-dialog");
        dialog.find("#shutdown-hub-label").html('关闭Hub');
        dialog.find(".shutdown-button").html('确定');
        dialog.find(".btn-default").html('取消');
        dialog.find("input[type=checkbox]").prop("checked", true);
        dialog.modal();
    });

    $("#shutdown-hub-dialog").find(".shutdown-button").click(function () {
        var dialog = $("#shutdown-hub-dialog");
        var servers = dialog.find(".shutdown-servers-checkbox").prop("checked");
        var proxy = dialog.find(".shutdown-proxy-checkbox").prop("checked");
        api.shutdown_hub({
            proxy: proxy,
            servers: servers,
        });
    });
    
});
